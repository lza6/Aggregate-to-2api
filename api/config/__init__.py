"""imagefree_api 配置包。全部可用环境变量覆盖，便于部署。

由原单体 api/config.py 拆分而来：
- 子配置类（DBSettings 等）各放入独立子模块，并暴露 ``from_settings(cls, s)`` 工厂
  把 Settings 字段聚合进对应子配置（P0-F1 下沉：原 _resolve_proxy_and_init_groups 内联
  构造逻辑全部移至各子模块的 from_settings）。
- Settings 类、模块级单例 ``settings``、全部模块级常量与 ``apply_model`` 保留在本模块
  （`from api.config import Settings / settings / BASE_URL ...` 完全向后兼容）。
- `from api.config import config` 兼容：config 指向本包模块本身。
- `from api.config.settings import ...` 兼容：见 api/config/settings.py。
- Settings 级聚合函数（apply_adaptive_defaults / validate_settings / settings_json）
  下沉至 base.py（duck typing，避免循环 import）。

使用 pydantic-settings 集中管理配置，保持 IF_ 前缀环境变量向后兼容。
"""

from __future__ import annotations

import os
import sys
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .base import apply_adaptive_defaults, settings_json, validate_settings
from .cache import CacheSettings
from .db import DBSettings
from .edit import EditSettings
from .http import HTTPSettings
from .observability import ObservabilitySettings
from .pool import PoolSettings
from .provider import ProviderSettings
from .queue import QueueSettings
from .security import SecuritySettings
from .solver import SolverSettings

# ── 顶层 Settings 类 ──────────────────────────────────────


class Settings(BaseSettings):
    """imagefree-api 全局配置。

    所有环境变量使用 IF_ 前缀。通过 validation_alias 映射到字段名。
    子配置类通过属性访问（如 settings.db.file）。
    """

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    # ── 空串环境变量容忍 ──
    # 部署模板常以 `IF_XXX=` 留空表示「用默认」，pydantic 会因 int/bool 空串崩溃。
    # 在组装层直接丢弃所有空字符串键 → 交由 Field 默认值或后续自适应接管。
    @model_validator(mode="before")
    @classmethod
    def _drop_blank_env(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if not (isinstance(v, str) and v.strip() == "")}
        return data

    # ── Solver ──
    base_url: str = Field("https://imagefree.net", validation_alias="IF_BASE_URL")
    sitekey: str = Field("0x4AAAAAACE-XLGoQUckKKm_", validation_alias="IF_SITEKEY")
    cf_solver_url: str = Field("http://127.0.0.1:8001", validation_alias="IF_CF_SOLVER_URL")
    cf_solver_urls: str | list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:8001"], validation_alias="IF_CF_SOLVER_URLS"
    )
    solver_node_weights: str | dict[str, int] = Field(default_factory=dict, validation_alias="IF_SOLVER_NODE_WEIGHTS")
    solver_rate_limit_cooldown_seconds: float = Field(60.0, validation_alias="IF_SOLVER_RATE_LIMIT_COOLDOWN_SECONDS")
    # P1-6 IdleTimeout：节点空闲超过该秒数标记 idle，select_node 优先非 idle 节点；
    # 0=关闭（向后兼容）。参考 nvidia-playgroud-go Pool.IdleTimeout 按需停池。
    solver_idle_timeout_seconds: float = Field(0.0, validation_alias="IF_SOLVER_IDLE_TIMEOUT_SECONDS")

    # ── HTTP ──
    host: str = Field("127.0.0.1", validation_alias="IF_HOST")
    port: int = Field(8100, validation_alias="IF_PORT")
    proxy: str | None = Field(default=None, validation_alias="IF_PROXY")

    @field_validator("proxy", mode="after")
    @classmethod
    def _normalize_empty_proxy(cls, v: str | None) -> str | None:
        """空串代理统一归一化为 None（直连）。

        docker-compose 里 IF_PROXY= 显式清空代理时会注入空字符串；
        httpx 对空串抛 "Unknown scheme for proxy URL URL('')"，
        在源头归一化，所有 proxy=config.PROXY 的调用点自然安全。
        """
        if isinstance(v, str) and not v.strip():
            return None
        return v

    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    )
    if_http_max_connections: int = Field(100, validation_alias="IF_HTTP_MAX_CONNECTIONS")
    if_http_keepalive: int = Field(20, validation_alias="IF_HTTP_KEEPALIVE")
    if_upstream_max_inflight: int = Field(30, validation_alias="IF_UPSTREAM_MAX_INFLIGHT")
    # P0-安全：请求体总量上限（防恶意大 base64 正文在 4MB/张校验前占满内存）
    if_max_request_body: int = Field(8 * 1024 * 1024, validation_alias="IF_MAX_REQUEST_BODY")

    # ── Turnstile / Solver ──
    turnstile_timeout: int = Field(90, validation_alias="IF_TURNSTILE_TIMEOUT")
    turnstile_poll_interval: float = Field(2.0, validation_alias="IF_TURNSTILE_POLL_INTERVAL")
    healthz_cache_ttl: int = Field(5, validation_alias="IF_HEALTHZ_CACHE_TTL")
    token_prefetch_concurrency: int = Field(1, validation_alias="IF_TOKEN_PREFETCH_CONCURRENCY")
    if_prefetch_after_solve_delay: float = Field(0.0, validation_alias="IF_PREFETCH_AFTER_SOLVE_DELAY")
    if_prefetch_ema_alpha: float = Field(0.3, validation_alias="IF_PREFETCH_EMA_ALPHA")
    solve_circuit_threshold: int = Field(5, validation_alias="IF_SOLVE_CIRCUIT_THRESHOLD")
    solve_circuit_probe_seconds: int = Field(30, validation_alias="IF_SOLVE_CIRCUIT_PROBE_SECONDS")
    solve_stats_window_seconds: int = Field(300, validation_alias="IF_SOLVE_STATS_WINDOW_SECONDS")

    # ── 存储驱动（ISSUE-01 Storage Adapter）──
    # IF_STORAGE_BACKEND: 'sqlite'（默认单机，无需外置依赖）| 'redis'（集群）
    # IF_REDIS_URL 复用「缓存/Redis」分组的 if_redis_url 字段（见下），不另设。
    if_storage_backend: str = Field("sqlite", validation_alias="IF_STORAGE_BACKEND")

    # ── 超时 / 轮询 ──
    generate_timeout: int = Field(300, validation_alias="IF_GENERATE_TIMEOUT")
    generate_poll_interval: float = Field(2.0, validation_alias="IF_GENERATE_POLL_INTERVAL")
    edit_timeout: int = Field(3600, validation_alias="IF_EDIT_TIMEOUT")
    task_hard_timeout: int = Field(480, validation_alias="IF_TASK_HARD_TIMEOUT")
    edit_concurrency_wait: int = Field(60, validation_alias="IF_EDIT_CONCURRENCY_WAIT")
    edit_mutex_enabled: bool = Field(True, validation_alias="IF_EDIT_MUTEX_ENABLED")
    edit_lease_enabled: bool = Field(False, validation_alias="IF_EDIT_LEASE_ENABLED")
    edit_lease_ttl: int = Field(30, validation_alias="IF_EDIT_LEASE_TTL")
    edit_lock_max_age: int = Field(1500, validation_alias="IF_EDIT_LOCK_MAX_AGE")
    edit_retry_max: int = Field(30, validation_alias="IF_EDIT_RETRY_MAX")
    edit_retry_interval: int = Field(20, validation_alias="IF_EDIT_RETRY_INTERVAL")
    edit_proxy_file: str = Field("", validation_alias="IF_EDIT_PROXY_FILE")
    edit_proxy_parallel: int = Field(1, validation_alias="IF_EDIT_PROXY_PARALLEL")
    if_edit_proxy_max_inflight: int = Field(2, validation_alias="IF_EDIT_PROXY_MAX_INFLIGHT")
    edit_proxy_pool_size: int = Field(1, validation_alias="IF_EDIT_PROXY_POOL_SIZE")
    edit_proxy_pool_idle_ttl: int = Field(180, validation_alias="IF_EDIT_PROXY_POOL_IDLE_TTL")
    generate_max_attempts: int = Field(2, validation_alias="IF_GENERATE_MAX_ATTEMPTS")
    if_txt_retry_max: int = Field(3, validation_alias="IF_TXT_RETRY_MAX")
    if_txt_retry_backoff_base: int = Field(5, validation_alias="IF_TXT_RETRY_BACKOFF_BASE")
    token_wait_timeout: int = Field(30, validation_alias="IF_TOKEN_WAIT_TIMEOUT")
    sync_timeout: int = Field(300, validation_alias="IF_SYNC_TIMEOUT")

    # ── 队列 / Worker（服务器规格自适应默认值）──
    # 默认值在运行时由 system_spec 的 ADAPTIVE_* 覆盖（见 apply_adaptive_defaults）
    max_queue: int = Field(2000, validation_alias="IF_MAX_QUEUE")
    admin_queue_max: int = Field(200, validation_alias="IF_ADMIN_QUEUE_MAX")
    high_queue_max: int = Field(500, validation_alias="IF_HIGH_QUEUE_MAX")
    normal_queue_max: int = Field(1500, validation_alias="IF_NORMAL_QUEUE_MAX")
    workers: int = Field(10, validation_alias="IF_WORKERS")
    if_worker_auto: bool = Field(False, validation_alias="IF_WORKER_AUTO")
    if_workers_min: int = Field(4, validation_alias="IF_WORKERS_MIN")
    if_workers_max: int = Field(16, validation_alias="IF_WORKERS_MAX")
    if_worker_scale_up_threshold: int = Field(200, validation_alias="IF_WORKER_SCALE_UP_THRESHOLD")
    if_worker_scale_down_threshold: int = Field(20, validation_alias="IF_WORKER_SCALE_DOWN_THRESHOLD")
    if_worker_idle_seconds: int = Field(90, validation_alias="IF_WORKER_IDLE_SECONDS")
    # v8.0 P1-5: 缩容防抖动持续秒数（低负载必须持续该秒数才缩容，避免瞬时抖动）
    if_worker_scale_down_hold: int = Field(30, validation_alias="IF_WORKER_SCALE_DOWN_HOLD")
    # v8.0 P1-5: 旧单维扩缩容 fallback（True 走 queue-depth-only 旧逻辑；False 走多维评分）
    if_worker_scaler_legacy: bool = Field(False, validation_alias="IF_WORKER_SCALER_LEGACY")
    # v8.0 P1-8：持久化队列默认开启——重启不丢未完成任务（queue.db 持久化 + replay）
    if_persistent_queue_enabled: bool = Field(True, validation_alias="IF_PERSISTENT_QUEUE_ENABLED")
    if_persistent_queue_db: str = Field("data/queue.db", validation_alias="IF_PERSISTENT_QUEUE_DB")
    # worker 批量调度（可选优化）：启用后 worker 按小批次消费队列减少上下文切换
    if_worker_batch_enabled: bool = Field(False, validation_alias="IF_WORKER_BATCH_ENABLED")
    if_worker_batch_size: int = Field(5, validation_alias="IF_WORKER_BATCH_SIZE")

    # ── Token 池 ──
    token_pool_size: int = Field(6, validation_alias="IF_TOKEN_POOL_SIZE")
    token_ttl: int = Field(90, validation_alias="IF_TOKEN_TTL")
    # P0-3 双水位 + 批量并发填充（吞吐工程化，参考 free-api/nvidia-playgourd-go）。
    # direct 池无排队时维持的目标水位（预热数，提升零延迟命中率）；默认 1 = 旧逻辑（维持1个）。
    # 生产建议配 5：池始终保持 5 个新鲜 token，零延迟命中率高，请求不阻塞在求解。
    token_target_watermark: int = Field(1, ge=0, validation_alias="IF_TOKEN_TARGET_WATERMARK")
    # 紧急水位：total 低于此值时触发批量并发填充（防池空干等）；默认 0 = 关闭批量（单次填充）。
    token_urgent_watermark: int = Field(0, ge=0, validation_alias="IF_TOKEN_URGENT_WATERMARK")
    # 批量并发填充数：urgent 时一次并发 N 个 solve（gather）；默认 1 = 单次（向后兼容）。
    # 真并发需 cf_solver 支持多槽（P0-1 page_count>1）+ TOKEN_PREFETCH_CONCURRENCY >= N。
    token_batch_fill_size: int = Field(1, ge=1, validation_alias="IF_TOKEN_BATCH_FILL_SIZE")

    # ── 画廊 ──
    gallery_limit: int = Field(50, validation_alias="IF_GALLERY_LIMIT")
    if_gallery_password: str = Field("", validation_alias="IF_GALLERY_PASSWORD")
    # P1-1 画廊签名 URL：HMAC 签名 + TTL 过期，替代单一静态密码（防盗链/防爬取）。
    # 签名密钥；为空且未配 IF_GALLERY_PASSWORD 时画廊开放（向后兼容）。
    if_gallery_signing_secret: str = Field("", validation_alias="IF_GALLERY_SIGNING_SECRET")
    # 签名有效时长（秒）；默认 600s。仅校验 exp，不绑 IP（CGNAT/代理下 IP 漂移会误杀）。
    if_gallery_signing_ttl: int = Field(600, validation_alias="IF_GALLERY_SIGNING_TTL")
    # ── 成本 / 预算（M6-F3 成本可视化）──
    # 每积分折算美元（图片成本估算：credits_used * IF_USD_PER_CREDIT）；0 = 不估算图片成本
    if_usd_per_credit: float = Field(0.0, validation_alias="IF_USD_PER_CREDIT")
    # 月度预算（美元）；0 = 不启用成本告警（cost_over_budget / cost_burn_rate_warning）
    if_cost_budget_usd: float = Field(0.0, validation_alias="IF_COST_BUDGET_USD")
    # v4.2.1: CORS 来源白名单（逗号分隔；默认 * 全放行向后兼容）
    if_cors_origins: str = Field("*", validation_alias="IF_CORS_ORIGINS")
    # P3-3: 生产安全响应头注入开关（默认开启；关闭=最小回滚，不注入任何安全头）。
    # 仅当 True 时 SecurityHeadersMiddleware 注入 X-Content-Type-Options / X-Frame-Options /
    # Referrer-Policy / Strict-Transport-Security（仅 HTTPS）。默认 true 不破坏现状：
    # 本 API 为 JSON 接口+管理面板，这些头对现有 JS 前端无破坏（JSON 响应无 inline HTML）。
    if_security_headers_enabled: bool = Field(True, validation_alias="IF_SECURITY_HEADERS_ENABLED")
    # P3-3: 宽松 CSP 响应头开关（默认关闭，避免误杀管理面板 inline script / 画廊 CDN 图片）。
    if_csp_enabled: bool = Field(False, validation_alias="IF_CSP_ENABLED")
    # v4.4: 全局 API Key 防滥用（逗号分隔多个；空 = 开放模式）
    if_api_keys: str = Field("", validation_alias="IF_API_KEYS")
    if_chat_rate_limit: int = Field(60, validation_alias="IF_CHAT_RATE_LIMIT")

    # ── tryingopen.com 匿名网关（v4.4 聊天）──────────────────
    # 开关：字符串 '1'/'true'/'on' → True（走 _bool_str_coerce）。原先 os.getenv 直读，现纳入模型。
    if_tryingopen_enabled: bool = Field(True, validation_alias="IF_TRYINGOPEN_ENABLED")
    # 每出口每小时额度（remaining_credits 估算用；0 = 不计配额）
    if_tryingopen_hourly_per_ip: int = Field(20, validation_alias="IF_TRYINGOPEN_HOURLY_PER_IP")
    # 代理轮换最大尝试次数（之后追加一次直连兜底）；钳到 >=1，防误配 0/负数导致聊天静默无输出
    if_tryingopen_max_attempts: int = Field(3, ge=1, validation_alias="IF_TRYINGOPEN_MAX_ATTEMPTS")
    # 模型目录同步间隔（分钟）
    if_tryingopen_sync_minutes: int = Field(30, validation_alias="IF_TRYINGOPEN_SYNC_MINUTES")

    # ── 缓存 ──
    if_lru_cache_size: int = Field(512, validation_alias="IF_LRU_CACHE_SIZE")
    if_lru_cache_ttl: int = Field(10, validation_alias="IF_LRU_CACHE_TTL")
    if_redis_enabled: bool = Field(False, validation_alias="IF_REDIS_ENABLED")
    if_redis_url: str = Field("redis://localhost:6379/0", validation_alias="IF_REDIS_URL")
    # ── TensorFeed AI 生态（v6.7.0）──
    if_tensorfeed_cache_ttl: int = Field(900, validation_alias="IF_TENSORFEED_CACHE_TTL")
    if_tensorfeed_base: str = Field("https://tensorfeed.ai", validation_alias="IF_TENSORFEED_BASE")

    # ── 可观测性 ──
    if_health_check_interval: int = Field(60, validation_alias="IF_HEALTH_CHECK_INTERVAL")
    if_health_check_enabled: bool = Field(True, validation_alias="IF_HEALTH_CHECK_ENABLED")
    if_alert_check_interval: int = Field(60, validation_alias="IF_ALERT_CHECK_INTERVAL")
    # P2-3 告警 webhook 外发（企业微信/钉钉/Slack 通用 JSON POST；空 = 不外发）
    if_alert_webhook_url: str = Field("", validation_alias="IF_ALERT_WEBHOOK_URL")
    # P13: 磁盘日志落盘（空 = 关闭；默认 data/logs）
    if_log_dir: str = Field("data/logs", validation_alias="IF_LOG_DIR")
    if_log_retention_days: int = Field(14, validation_alias="IF_LOG_RETENTION_DAYS")

    # ── v8.1 P1-A agent 化能力跃迁开关 ──
    # P1-A1 skills 四件套体系（api/skills/<scene>/SKILL.md + frontmatter 索引）
    if_agent_skills_enabled: bool = Field(True, validation_alias="IF_AGENT_SKILLS_ENABLED")
    # P1-A2 意图分类→Provider/Skill 路由层（规则正则兜底 + LLM 仅处理模糊意图）
    if_agent_intent_classifier: bool = Field(True, validation_alias="IF_AGENT_INTENT_CLASSIFIER")
    # P1-A3 L0-L3 记忆分层 + 异步巩固管道（复用 imagefree.db 加 mem_* 表）
    if_memory_consolidation_enabled: bool = Field(True, validation_alias="IF_MEMORY_CONSOLIDATION_ENABLED")
    # 记忆巩固后台 worker 周期（秒，默认 300s）
    if_memory_consolidation_interval: float = Field(300.0, validation_alias="IF_MEMORY_CONSOLIDATION_INTERVAL")
    # P1-A4 provider 风险档案 Tier + PreToolUse 硬门禁（paid Tier 默认拦截真实付费）
    if_provider_risk_tier: bool = Field(True, validation_alias="IF_PROVIDER_RISK_TIER")
    # P1-A7 独立终检 Agent（交付前 LLM 审查，用 tryingopen 免费上游）
    if_critic_agent_enabled: bool = Field(True, validation_alias="IF_CRITIC_AGENT_ENABLED")

    # ── DB ──
    stats_file: str = Field("data/stats.json", validation_alias="IF_STATS_FILE")
    db_file: str = Field("data/imagefree.db", validation_alias="IF_DB_FILE")
    # P3-1: 路由决策持久化（独立轻量 sqlite，不侵入主 DB schema）；空 = 关闭（默认）
    routing_db_file: str = Field("", validation_alias="IF_ROUTING_DB")
    if_base64_dir: str = Field("data/imgs", validation_alias="IF_BASE64_DIR")
    if_base64_file_ttl: int = Field(86400, validation_alias="IF_BASE64_FILE_TTL")
    # S-14: base64 文件目录配额上限（GB），超过后按最旧优先清理至 80 %
    if_img_max_gb: float = Field(5.0, validation_alias="IF_IMG_MAX_GB")
    db_retention_days: int = Field(365, validation_alias="IF_DB_RETENTION_DAYS")
    db_cleanup_interval: int = Field(21600, validation_alias="IF_DB_CLEANUP_INTERVAL")
    if_db_batch_enabled: bool = Field(True, validation_alias="IF_DB_BATCH_ENABLED")
    if_db_batch_window: float = Field(0.5, validation_alias="IF_DB_BATCH_WINDOW")
    if_db_pool_size: int = Field(5, validation_alias="IF_DB_POOL_SIZE")
    if_db_pool_timeout: int = Field(10, validation_alias="IF_DB_POOL_TIMEOUT")

    # ── Provider / 代理池 / 号池 ──
    proxy_file: str = Field("", validation_alias="IF_PROXY_FILE")
    free_proxy_enabled: bool = Field(False, validation_alias="IF_FREE_PROXY")
    free_proxy_refresh_min: int = Field(30, validation_alias="IF_FREE_PROXY_REFRESH_MIN")
    proxy_cooldown_seconds: int = Field(120, validation_alias="IF_PROXY_COOLDOWN_SECONDS")
    if_proxy_max_use_per_day: int = Field(1, validation_alias="IF_PROXY_MAX_USE_PER_DAY")
    if_proxy_use_cooldown_map: str = Field("0,30,90,300,900", validation_alias="IF_PROXY_USE_COOLDOWN_MAP")
    # P1-4: 出口粘滞窗口（秒）——同 session_id 复用同出口，防上游 IP 跳变风控；0=关闭
    if_proxy_sticky_window: int = Field(300, validation_alias="IF_PROXY_STICKY_WINDOW")
    # ── Cloudflare trace 出口探测器（v6.7.x）──
    # 通过 cdn-cgi/trace 探测每个免费代理的真实出口 IP/colo，回填进 ProxyEntry，
    # 让 snapshot 透出真实出口信息（覆盖 md5 假 latency）。默认关闭（零网络开销）。
    if_proxy_trace_enabled: bool = Field(False, validation_alias="IF_PROXY_TRACE_ENABLED")
    if_proxy_trace_ttl: int = Field(3600, validation_alias="IF_PROXY_TRACE_TTL")
    if_proxy_trace_max_per_round: int = Field(50, validation_alias="IF_PROXY_TRACE_MAX_PER_ROUND")
    if_proxy_trace_concurrency: int = Field(8, validation_alias="IF_PROXY_TRACE_CONCURRENCY")
    account_db_file: str = Field("data/account_pool.db", validation_alias="IF_ACCOUNT_DB_FILE")
    email_db_file: str = Field("data/email_registry.db", validation_alias="IF_EMAIL_DB_FILE")
    nanobanana_account_target: int = Field(10000, validation_alias="IF_NANOBANANA_ACCOUNT_TARGET")
    account_auto: bool = Field(True, validation_alias="IF_ACCOUNT_AUTO")
    mock_register: bool = Field(False, validation_alias="IF_MOCK_REGISTER")
    # AI 兜底邮件验证码/验证链接提取（默认关闭；正则未命中时降级 LLM）
    if_mail_ai_extract: bool = Field(False, validation_alias="IF_MAIL_AI_EXTRACT")
    if_provider_degrade_threshold: int = Field(3, validation_alias="IF_PROVIDER_DEGRADE_THRESHOLD")
    if_provider_recover_interval: int = Field(300, validation_alias="IF_PROVIDER_RECOVER_INTERVAL")
    if_idempotency_enabled: bool = Field(False, validation_alias="IF_IDEMPOTENCY_ENABLED")
    if_idempotency_ttl: int = Field(900, validation_alias="IF_IDEMPOTENCY_TTL")
    if_dlq_enabled: bool = Field(True, validation_alias="IF_DLQ_ENABLED")
    if_dlq_max_retries: int = Field(3, validation_alias="IF_DLQ_MAX_RETRIES")
    if_dlq_retention_days: int = Field(7, validation_alias="IF_DLQ_RETENTION_DAYS")
    # S-9: DLQ 真重入队（默认关——重入可能被刷；开启后 retry 端点把任务放回优先级队列）
    if_dlq_requeue: bool = Field(False, validation_alias="IF_DLQ_REQUEUE")
    # S-4: 慢日志画像（C2/C3）——阈值/容量/开关
    if_slow_log_enabled: bool = Field(True, validation_alias="IF_SLOW_LOG_ENABLED")
    if_slow_request_ms: float = Field(5000.0, validation_alias="IF_SLOW_REQUEST_MS")
    if_slow_log_size: int = Field(500, validation_alias="IF_SLOW_LOG_SIZE")
    default_model: str = Field("default", validation_alias="IF_DEFAULT_MODEL")
    reg_backoff_cf: float = Field(30.0, validation_alias="IF_REG_BACKOFF_CF")
    reg_backoff_email: float = Field(60.0, validation_alias="IF_REG_BACKOFF_EMAIL")
    reg_backoff_ip: float = Field(120.0, validation_alias="IF_REG_BACKOFF_IP")
    reg_backoff_transient_base: float = Field(2.0, validation_alias="IF_REG_BACKOFF_TRANSIENT_BASE")
    reg_backoff_transient_max: float = Field(30.0, validation_alias="IF_REG_BACKOFF_TRANSIENT_MAX")

    # ── fal.ai minimax-H3 视频提供商（Playwright 浏览器即服务）──
    if_falai_enabled: bool = Field(True, validation_alias="IF_FALAI_ENABLED")
    if_falai_hcaptcha_sitekey: str = Field(
        "79e0463a-f79a-4742-b3da-489afd1cbe68",
        validation_alias="IF_FALAI_HCAPTCHA_SITEKEY",
    )
    if_falai_hcaptcha_mode: str = Field("passive", validation_alias="IF_FALAI_HCAPTCHA_MODE")
    if_falai_browser_headful: bool = Field(True, validation_alias="IF_FALAI_BROWSER_HEADFUL")
    if_falai_browser_pool_size: int = Field(2, validation_alias="IF_FALAI_BROWSER_POOL_SIZE")
    if_falai_verify_timeout: int = Field(90, validation_alias="IF_FALAI_VERIFY_TIMEOUT")
    if_falai_poll_interval: float = Field(2.0, validation_alias="IF_FALAI_POLL_INTERVAL")
    if_falai_poll_timeout: int = Field(120, validation_alias="IF_FALAI_POLL_TIMEOUT")

    # ── 分组配置（延迟初始化，由 model_validator 填充）───────────────
    # 公开接口限速：每 IP 每分钟允许的生成提交次数（0 = 关闭限速）
    if_requests_per_minute: int = Field(10, validation_alias="IF_REQUESTS_PER_MINUTE")
    # L1 秒级令牌桶容量：突发并发上限（<=0 关闭 L1，退化为仅滑窗+daily_limit）；
    # None 时默认取 IF_REQUESTS_PER_MINUTE（与滑窗口径对齐）。
    if_rate_token_capacity: float | None = Field(None, validation_alias="IF_RATE_TOKEN_CAPACITY")
    # L1 令牌桶回填速率：每秒补充令牌数（0 = 不回填，纯突发桶）；回填走墙上时钟。
    if_rate_token_refill_per_sec: float = Field(0.0, validation_alias="IF_RATE_TOKEN_REFILL_PER_SEC")

    # ── 动态 IP 风控（ISSUE-02）────────────────────────────
    # 白名单：逗号分隔 IP，白名单 IP 直接绕过封禁与限速（如运维/监控探针）
    if_ip_whitelist: str = Field("", validation_alias="IF_IP_WHITELIST")
    # 受信代理：逗号分隔 IP。仅当 socket 对端命中时才解析 X-Forwarded-For（取最右非代理段），
    # 否则一律以 socket 对端为准（防 XFF 伪造绕过封禁/限流）。默认仅信任本机反代。
    if_trusted_proxies: str = Field("127.0.0.1,::1", validation_alias="IF_TRUSTED_PROXIES")
    # 频繁超限自动入黑名单：连续在窗口内超限达到阈值的 IP，自动封禁 TTL 秒
    if_auto_block_enabled: bool = Field(True, validation_alias="IF_AUTO_BLOCK_ENABLED")
    if_auto_block_threshold: int = Field(3, validation_alias="IF_AUTO_BLOCK_THRESHOLD")
    if_auto_block_window_seconds: int = Field(300, validation_alias="IF_AUTO_BLOCK_WINDOW_SECONDS")
    if_auto_block_ttl_seconds: int = Field(3600, validation_alias="IF_AUTO_BLOCK_TTL_SECONDS")
    # v7.7.13: 恶意 IP 永久封禁——True 时自动封禁 ttl=0（永不过期），防脚本刷资源 30 分钟解封后继续刷
    if_auto_block_permanent: bool = Field(False, validation_alias="IF_AUTO_BLOCK_PERMANENT")
    # ── 管理面（安全风控）独立 Key（ISSUE-02 加固）──────────
    # 优先使用独立管理 Key；为空则继承 IF_API_KEYS；两者皆空默认拒绝管理操作
    if_admin_keys: str = Field("", validation_alias="IF_ADMIN_KEYS")
    # 显式开放模式：仅当配置为空且设置 IF_ADMIN_KEY_OPEN=1（本地运维/内网）时放行管理端
    if_admin_key_open: bool = Field(False, validation_alias="IF_ADMIN_KEY_OPEN")
    # v7.7.4: 管理员申诉联系方式（被封禁用户可据此联系解封）。空=不展示。
    # 展示于安全风控页 + 封禁响应提示。仅管理端可见配置值，不泄露给匿名访客的写操作响应。
    if_admin_contact: str = Field("", validation_alias="IF_ADMIN_CONTACT")
    _db: DBSettings | None = None
    _http: HTTPSettings | None = None
    _solver: SolverSettings | None = None
    _cache: CacheSettings | None = None
    _provider: ProviderSettings | None = None
    _pool: PoolSettings | None = None
    _queue: QueueSettings | None = None
    _observability: ObservabilitySettings | None = None
    _edit: EditSettings | None = None
    _security: SecuritySettings | None = None

    @field_validator("proxy", mode="before")
    @classmethod
    def _proxy_empty_is_none(cls, v: str | None) -> str | None:
        """空字符串 → None，触发后续 fallback 到 HTTPS_PROXY/HTTP_PROXY。"""
        if v is None or v == "":
            return None
        return v

    @field_validator(
        "edit_mutex_enabled",
        "edit_lease_enabled",
        "if_worker_auto",
        "if_persistent_queue_enabled",
        "if_health_check_enabled",
        "if_db_batch_enabled",
        "free_proxy_enabled",
        "account_auto",
        "mock_register",
        "if_idempotency_enabled",
        "if_dlq_enabled",
        "if_auto_block_enabled",
        "if_auto_block_permanent",
        "if_admin_key_open",
        "if_proxy_trace_enabled",
        "if_falai_enabled",
        "if_falai_browser_headful",
        "if_security_headers_enabled",
        "if_csp_enabled",
        "if_tryingopen_enabled",
        mode="before",
    )
    @classmethod
    def _bool_str_coerce(cls, v: str | bool) -> bool:
        """'1'/'true'/'yes'/'on' → True 的字符串兼容。"""
        if isinstance(v, bool):
            return v
        return v.strip().lower() in {"1", "true", "yes", "on"}

    @model_validator(mode="after")
    def _resolve_proxy_and_init_groups(self) -> Settings:
        """代理 fallback 解析 + 服务器规格自适应并发（未显式设置时）+ 分组配置初始化。

        子配置构造下沉至各子模块的 ``from_settings(cls, s)`` 工厂方法（P0-F1），
        本方法仅做 proxy fallback + 自适应默认 + 委托构造。
        """
        # ── 代理 fallback ──
        if not self.proxy:
            for var in ("HTTPS_PROXY", "HTTP_PROXY"):
                val = os.environ.get(var)
                if val:
                    self.proxy = val
                    break

        # ── 服务器规格自适应并发（仅当用户未显式设置对应环境变量时生效）──
        apply_adaptive_defaults(self)

        # ── 分组配置（各子模块 from_settings 工厂，原内联构造逻辑下沉）──
        self._db = DBSettings.from_settings(self)
        self._http = HTTPSettings.from_settings(self)
        self._solver = SolverSettings.from_settings(self)
        self._cache = CacheSettings.from_settings(self)
        self._provider = ProviderSettings.from_settings(self)
        self._pool = PoolSettings.from_settings(self)
        self._queue = QueueSettings.from_settings(self)
        self._observability = ObservabilitySettings.from_settings(self)
        self._edit = EditSettings.from_settings(self)
        self._security = SecuritySettings.from_settings(self)
        # 模块级便捷引用（供 main.py 读取）
        global CORS_ORIGINS
        CORS_ORIGINS = self.if_cors_origins or "*"
        return self

    @property
    def db(self) -> DBSettings:
        assert self._db is not None
        return self._db

    @property
    def http(self) -> HTTPSettings:
        assert self._http is not None
        return self._http

    @property
    def solver(self) -> SolverSettings:
        assert self._solver is not None
        return self._solver

    @property
    def cache(self) -> CacheSettings:
        assert self._cache is not None
        return self._cache

    @property
    def provider(self) -> ProviderSettings:
        assert self._provider is not None
        return self._provider

    @property
    def pool(self) -> PoolSettings:
        assert self._pool is not None
        return self._pool

    @property
    def queue(self) -> QueueSettings:
        assert self._queue is not None
        return self._queue

    @property
    def observability(self) -> ObservabilitySettings:
        assert self._observability is not None
        return self._observability

    @property
    def edit(self) -> EditSettings:
        assert self._edit is not None
        return self._edit

    @property
    def security(self) -> SecuritySettings:
        assert self._security is not None
        return self._security

    def settings_json(self) -> dict:
        """导出完整配置快照（供 /v1/meta 扩展）。实现下沉至 base.py。"""
        return settings_json(self)

    def validate(self) -> list[str]:
        """启动时校验关键配置，返回错误列表。实现下沉至 base.py。"""
        return validate_settings(self)


# ── 模块级单例 ──────────────────────────────────────────
# P2-5: 模块级实例化改为工厂 + 测试钩子，缓解跨文件单例污染（v6.9.0 P0-1 根因）。
# 保留 `settings = Settings()` 模块级变量向后兼容（`from api.config import settings` 仍可用），
# 但新增 `get_settings()`（lru_cache 单例）+ `reset_settings()`（测试重置钩子）。
# 测试隔离改为调 reset_settings() 重建，而非 monkeypatch 字段重置（污染残留风险低）。
_settings_cache: Settings | None = None


def get_settings() -> Settings:
    """获取全局 Settings 单例（lru_cache 风格，首次调用时实例化）。

    生产与模块级 `settings` 等价；测试可用 reset_settings() 重建以隔离 env。
    """
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings()
    return _settings_cache


def reset_settings() -> Settings:
    """重置全局 Settings 单例（测试钩子）：丢弃缓存并重建。

    用法：测试 fixture 在 monkeypatch.setenv 后调 reset_settings()，使后续
    get_settings()/settings 读取新 env。返回新实例便于直接断言。

    同步刷新模块级 `settings` 全局变量（`from api.config import settings` 拿到新实例）。
    注意：模块级向后兼容常量（BASE_URL/TOKEN_POOL_SIZE 等）在 import 期已绑定旧值，
    **不会**自动刷新——需读这些常量的测试应改走 get_settings().xxx 或 settings.xxx。
    """
    global _settings_cache, settings
    _settings_cache = Settings()
    settings = _settings_cache
    return _settings_cache


settings = Settings()
_settings_cache = settings  # 工厂与模块级变量共享同一实例


# ── 模块级变量（保持向后兼容）───────────────────────────────
# Solver
BASE_URL = settings.base_url
SITEKEY = settings.sitekey
CF_SOLVER_URL = settings.solver.cf_solver_url
CF_SOLVER_URLS = settings.solver.cf_solver_urls
SOLVER_NODE_WEIGHTS = settings.solver.solver_node_weights
SOLVER_RATE_LIMIT_COOLDOWN_SECONDS = settings.solver.solver_rate_limit_cooldown_seconds
SOLVER_IDLE_TIMEOUT_SECONDS = settings.solver.solver_idle_timeout_seconds

# HTTP
HOST = settings.host
PORT = settings.port
PROXY = settings.proxy
USER_AGENT = settings.user_agent
IF_HTTP_MAX_CONNECTIONS = settings.if_http_max_connections
IF_HTTP_KEEPALIVE = settings.if_http_keepalive
IF_UPSTREAM_MAX_INFLIGHT = settings.if_upstream_max_inflight
IF_MAX_REQUEST_BODY = settings.if_max_request_body

# Turnstile / Solver
TURNSTILE_TIMEOUT = settings.turnstile_timeout
TURNSTILE_POLL_INTERVAL = settings.turnstile_poll_interval
HEALTHZ_CACHE_TTL = settings.healthz_cache_ttl
TOKEN_PREFETCH_CONCURRENCY = settings.token_prefetch_concurrency
IF_PREFETCH_AFTER_SOLVE_DELAY = settings.if_prefetch_after_solve_delay
IF_PREFETCH_EMA_ALPHA = settings.if_prefetch_ema_alpha
SOLVE_CIRCUIT_THRESHOLD = settings.solve_circuit_threshold
SOLVE_CIRCUIT_PROBE_SECONDS = settings.solve_circuit_probe_seconds
SOLVE_STATS_WINDOW_SECONDS = settings.solve_stats_window_seconds

# 超时 / 轮询
GENERATE_TIMEOUT = settings.generate_timeout
GENERATE_POLL_INTERVAL = settings.generate_poll_interval
EDIT_TIMEOUT = settings.edit_timeout
TASK_HARD_TIMEOUT = settings.task_hard_timeout
EDIT_CONCURRENCY_WAIT = settings.edit_concurrency_wait
EDIT_MUTEX_ENABLED = settings.edit_mutex_enabled
EDIT_LEASE_ENABLED = settings.edit_lease_enabled
EDIT_LEASE_TTL = settings.edit_lease_ttl
EDIT_LOCK_MAX_AGE = settings.edit_lock_max_age
EDIT_RETRY_MAX = settings.edit_retry_max
EDIT_RETRY_INTERVAL = settings.edit_retry_interval
EDIT_PROXY_FILE = settings.edit_proxy_file
EDIT_PROXY_PARALLEL = settings.edit_proxy_parallel
IF_EDIT_PROXY_MAX_INFLIGHT = settings.if_edit_proxy_max_inflight
EDIT_PROXY_POOL_SIZE = settings.edit_proxy_pool_size
EDIT_PROXY_POOL_IDLE_TTL = settings.edit_proxy_pool_idle_ttl
GENERATE_MAX_ATTEMPTS = settings.generate_max_attempts
IF_TXT_RETRY_MAX = settings.if_txt_retry_max
IF_TXT_RETRY_BACKOFF_BASE = settings.if_txt_retry_backoff_base
TOKEN_WAIT_TIMEOUT = settings.token_wait_timeout
SYNC_TIMEOUT = settings.sync_timeout

# 队列 / Worker
MAX_QUEUE = settings.max_queue
ADMIN_QUEUE_MAX = settings.admin_queue_max
HIGH_QUEUE_MAX = settings.high_queue_max
NORMAL_QUEUE_MAX = settings.normal_queue_max
WORKERS = settings.workers
IF_WORKER_AUTO = settings.if_worker_auto
IF_WORKERS_MIN = settings.if_workers_min
IF_WORKERS_MAX = settings.if_workers_max
IF_WORKER_SCALE_UP_THRESHOLD = settings.if_worker_scale_up_threshold
IF_WORKER_SCALE_DOWN_THRESHOLD = settings.if_worker_scale_down_threshold
IF_WORKER_IDLE_SECONDS = settings.if_worker_idle_seconds
IF_WORKER_SCALE_DOWN_HOLD = settings.if_worker_scale_down_hold
IF_WORKER_SCALER_LEGACY = settings.if_worker_scaler_legacy
IF_PERSISTENT_QUEUE_ENABLED = settings.if_persistent_queue_enabled
IF_PERSISTENT_QUEUE_DB = settings.if_persistent_queue_db
IF_WORKER_BATCH_ENABLED = settings.if_worker_batch_enabled
IF_WORKER_BATCH_SIZE = settings.if_worker_batch_size

# Token 池
TOKEN_POOL_SIZE = settings.token_pool_size
TOKEN_TTL = settings.token_ttl
# P0-3 双水位 + 批量并发填充
TOKEN_TARGET_WATERMARK = settings.token_target_watermark
TOKEN_URGENT_WATERMARK = settings.token_urgent_watermark
TOKEN_BATCH_FILL_SIZE = settings.token_batch_fill_size

# 画廊
GALLERY_LIMIT = settings.gallery_limit
IF_GALLERY_PASSWORD = settings.if_gallery_password
IF_GALLERY_SIGNING_SECRET = settings.if_gallery_signing_secret
IF_GALLERY_SIGNING_TTL = settings.if_gallery_signing_ttl

# 成本 / 预算（M6-F3）
IF_USD_PER_CREDIT = settings.if_usd_per_credit
IF_COST_BUDGET_USD = settings.if_cost_budget_usd

# 缓存
IF_LRU_CACHE_SIZE = settings.if_lru_cache_size
IF_LRU_CACHE_TTL = settings.if_lru_cache_ttl

# TensorFeed AI 生态（v6.7.0）
IF_TENSORFEED_CACHE_TTL = settings.if_tensorfeed_cache_ttl
IF_TENSORFEED_BASE = settings.if_tensorfeed_base

# 可观测性
IF_HEALTH_CHECK_INTERVAL = settings.if_health_check_interval
IF_HEALTH_CHECK_ENABLED = settings.if_health_check_enabled
IF_ALERT_CHECK_INTERVAL = settings.if_alert_check_interval
IF_ALERT_WEBHOOK_URL = settings.if_alert_webhook_url
# P13: 磁盘日志
IF_LOG_DIR = settings.if_log_dir
IF_LOG_RETENTION_DAYS = settings.if_log_retention_days

# ── mock 上游开关（E2E/CI；生产留空）──────────────
MOCK_UPSTREAM = os.getenv("IF_MOCK_UPSTREAM", "0").strip().lower() in {"1", "true", "yes", "on"}

# ── OpenTelemetry（IF_OTEL_*）───────────────────
OTEL_ENABLED = os.getenv("IF_OTEL_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
OTEL_SERVICE_NAME = os.getenv("IF_OTEL_SERVICE_NAME", "imagefree-api")
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("IF_OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
OTEL_CONSOLE_EXPORTER = os.getenv("IF_OTEL_CONSOLE_EXPORTER", "0").strip().lower() in {"1", "true", "yes", "on"}
# P3-2: tail-based 采样策略 —— 错误请求（5xx/异常）100% 采样，正常请求按比例采样。
# 默认 sample_rate=0.1（10%），error_sample_rate=1.0（100%）。生产建议调低 sample_rate 到 0.05。
OTEL_SAMPLE_RATE = float(os.getenv("IF_OTEL_SAMPLE_RATE", "0.1"))
OTEL_ERROR_SAMPLE_RATE = float(os.getenv("IF_OTEL_ERROR_SAMPLE_RATE", "1.0"))

# DB
STATS_FILE = settings.stats_file
DB_FILE = settings.db_file
IF_ROUTING_DB = settings.routing_db_file
IF_BASE64_DIR = settings.if_base64_dir
IF_BASE64_FILE_TTL = settings.if_base64_file_ttl
IF_IMG_MAX_GB = settings.if_img_max_gb
DB_RETENTION_DAYS = settings.db_retention_days
DB_CLEANUP_INTERVAL = settings.db_cleanup_interval
IF_DB_BATCH_ENABLED = settings.if_db_batch_enabled
IF_DB_BATCH_WINDOW = settings.if_db_batch_window
IF_DB_POOL_SIZE = settings.if_db_pool_size
IF_DB_POOL_TIMEOUT = settings.if_db_pool_timeout

# Provider / 代理池 / 号池
PROXY_FILE = settings.proxy_file
FREE_PROXY_ENABLED = settings.free_proxy_enabled
FREE_PROXY_REFRESH_MIN = settings.free_proxy_refresh_min
PROXY_COOLDOWN_SECONDS = settings.proxy_cooldown_seconds
IF_PROXY_MAX_USE_PER_DAY = settings.if_proxy_max_use_per_day
IF_PROXY_USE_COOLDOWN_MAP = settings.if_proxy_use_cooldown_map
IF_PROXY_STICKY_WINDOW = settings.if_proxy_sticky_window
# Cloudflare trace 出口探测器（v6.7.x）
IF_PROXY_TRACE_ENABLED = settings.if_proxy_trace_enabled
IF_PROXY_TRACE_TTL = settings.if_proxy_trace_ttl
IF_PROXY_TRACE_MAX_PER_ROUND = settings.if_proxy_trace_max_per_round
IF_PROXY_TRACE_CONCURRENCY = settings.if_proxy_trace_concurrency
ACCOUNT_DB_FILE = settings.account_db_file
EMAIL_DB_FILE = settings.email_db_file
NANOBANANA_ACCOUNT_TARGET = settings.nanobanana_account_target
ACCOUNT_AUTO = settings.account_auto
MOCK_REGISTER = settings.mock_register
IF_MAIL_AI_EXTRACT = settings.if_mail_ai_extract
IF_PROVIDER_DEGRADE_THRESHOLD = settings.if_provider_degrade_threshold
IF_PROVIDER_RECOVER_INTERVAL = settings.if_provider_recover_interval
IF_IDEMPOTENCY_ENABLED = settings.if_idempotency_enabled
IF_IDEMPOTENCY_TTL = settings.if_idempotency_ttl
IF_DLQ_ENABLED = settings.if_dlq_enabled
IF_DLQ_MAX_RETRIES = settings.if_dlq_max_retries
IF_DLQ_RETENTION_DAYS = settings.if_dlq_retention_days
IF_DLQ_REQUEUE = settings.if_dlq_requeue

# S-4: 慢日志画像（C2/C3）
IF_SLOW_LOG_ENABLED = settings.if_slow_log_enabled
IF_SLOW_REQUEST_MS = settings.if_slow_request_ms
IF_SLOW_LOG_SIZE = settings.if_slow_log_size
DEFAULT_MODEL = settings.default_model
REG_BACKOFF_CF = settings.reg_backoff_cf
REG_BACKOFF_EMAIL = settings.reg_backoff_email
REG_BACKOFF_IP = settings.reg_backoff_ip
REG_BACKOFF_TRANSIENT_BASE = settings.reg_backoff_transient_base
REG_BACKOFF_TRANSIENT_MAX = settings.reg_backoff_transient_max
# fal.ai minimax-H3 视频提供商（Playwright 浏览器即服务）
IF_FALAI_ENABLED = settings.if_falai_enabled
IF_FALAI_HCAPTCHA_SITEKEY = settings.if_falai_hcaptcha_sitekey
IF_FALAI_HCAPTCHA_MODE = settings.if_falai_hcaptcha_mode
IF_FALAI_BROWSER_HEADFUL = settings.if_falai_browser_headful
IF_FALAI_BROWSER_POOL_SIZE = settings.if_falai_browser_pool_size
IF_FALAI_VERIFY_TIMEOUT = settings.if_falai_verify_timeout
IF_FALAI_POLL_INTERVAL = settings.if_falai_poll_interval
IF_FALAI_POLL_TIMEOUT = settings.if_falai_poll_timeout
# 公开接口限速（0 = 关闭）
IF_REQUESTS_PER_MINUTE = settings.if_requests_per_minute
# L1 秒级令牌桶（None = 默认取 IF_REQUESTS_PER_MINUTE；<=0 关闭 L1）
IF_RATE_TOKEN_CAPACITY = settings.if_rate_token_capacity
IF_RATE_TOKEN_REFILL_PER_SEC = settings.if_rate_token_refill_per_sec

# ── 存储驱动（ISSUE-01）──────────────────────────
IF_STORAGE_BACKEND = settings.if_storage_backend
IF_REDIS_URL = settings.if_redis_url
IF_REDIS_ENABLED = settings.if_redis_enabled

# ── 动态 IP 风控（ISSUE-02）──────────────────────
IF_IP_WHITELIST = settings.if_ip_whitelist
IF_TRUSTED_PROXIES = settings.if_trusted_proxies
IF_AUTO_BLOCK_ENABLED = settings.if_auto_block_enabled
IF_AUTO_BLOCK_THRESHOLD = settings.if_auto_block_threshold
IF_AUTO_BLOCK_WINDOW_SECONDS = settings.if_auto_block_window_seconds
IF_AUTO_BLOCK_TTL_SECONDS = settings.if_auto_block_ttl_seconds
IF_AUTO_BLOCK_PERMANENT = settings.if_auto_block_permanent

# ── 管理面（安全风控）独立 Key（ISSUE-02 加固）──────────
IF_ADMIN_KEYS = settings.if_admin_keys
IF_ADMIN_KEY_OPEN = settings.if_admin_key_open
IF_ADMIN_CONTACT = settings.if_admin_contact

# ── CORS 白名单（模块级便捷引用；运行时不可变，直接读 settings.if_cors_origins 修改）──
CORS_ORIGINS = "*"

# ── tryingopen.com 匿名网关（模块级便捷引用）────────────────
IF_TRYINGOPEN_ENABLED = settings.if_tryingopen_enabled
IF_TRYINGOPEN_HOURLY_PER_IP = settings.if_tryingopen_hourly_per_ip
IF_TRYINGOPEN_MAX_ATTEMPTS = settings.if_tryingopen_max_attempts
IF_TRYINGOPEN_SYNC_MINUTES = settings.if_tryingopen_sync_minutes

# ── P3-3 安全头开关（模块级便捷引用）────────────────
IF_SECURITY_HEADERS_ENABLED = settings.if_security_headers_enabled
IF_CSP_ENABLED = settings.if_csp_enabled


# ── 纯常量 + apply_model（P0-2: 拆分到 .presets，re-export 保持向后兼容）──
# MAX_IMAGE_BYTES / MAX_PROMPT_LEN / ASPECT_RATIOS / MODEL_PRESETS / apply_model
# 详见 api/config/presets.py（dispatch/worker/imagefree/health/models 消费）
from .presets import (  # noqa: F401  (re-export for backward compat)
    ASPECT_RATIOS,
    MAX_IMAGE_BYTES,
    MAX_PROMPT_LEN,
    MODEL_PRESETS,
    apply_model,
)

# ── 兼容：`from api.config import config` 使 config 指代包模块本身 ──
config = sys.modules[__name__]


# ── 导出所有模块级变量名 ──────────────────────────────────
# 与 settings.py 一致：程序化生成 __all__，覆盖所有非下划线开头的模块级名字
# （含顶部 import 的子配置类、Settings、工厂函数、模块级常量、presets re-export、config）。
# 这样 `from api.config import *` 与显式 __all__ 行为一致，且无需手工维护 180+ 行名单。
__all__ = [name for name in globals() if not name.startswith("_")]
