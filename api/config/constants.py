"""模块级便捷常量快照（v22 P2-3 / A12 从 __init__.py 拆出）。

这些是 `from api.config import HOST / PORT / ...` 的向后兼容读点，在 import 期
从 settings 单例取一次值绑定为普通模块属性（**快照语义**，非惰性）。

注意：reset_settings() 后这些常量**不会**自动刷新（import 期已绑定旧值）——
需要跟随 env 变化的读点应改走 get_settings().xxx。

monkeypatch 读点必须用 `_pkg_attr(name)`（见 __init__.py），
它运行时读 api.config 包命名空间，因此 setattr("api.config.HOST", ...) 生效。
"""

from __future__ import annotations

from .otlp import (  # noqa: F401
    OTEL_CONSOLE_EXPORTER,
    OTEL_ENABLED,
    OTEL_ERROR_SAMPLE_RATE,
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_SAMPLE_RATE,
    OTEL_SERVICE_NAME,
)
from .presets import (  # noqa: F401
    ASPECT_RATIOS,
    MAX_IMAGE_BYTES,
    MAX_PROMPT_LEN,
    MODEL_PRESETS,
    apply_model,
)
from .settings_core import get_settings, settings  # noqa: F401

# ── Solver ──
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
IF_TXT_MAX_INFLIGHT = settings.if_txt_max_inflight
IF_TXT_SLOT_WAIT = settings.if_txt_slot_wait
IF_TXT_SLOT_STALE = settings.if_txt_slot_stale
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
# P0-4: 任务取消端点开关（POST /v1/tasks/{id}/cancel；缺省 1 开启）
IF_TASK_CANCEL_ENABLED = settings.if_task_cancel_enabled

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
# P2-9 成本预测预警推送阈值（%，0=关闭）
IF_COST_ALERT_PCT = settings.if_cost_alert_pct

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


# 函数式读取（走 get_settings() 工厂，P0-2 收敛后统一调用方）：
def mock_upstream() -> bool:
    """IF_MOCK_UPSTREAM 是否开启。默认 False：agent 真实调用 tryingopen。测试可显式置 1。"""
    return get_settings().if_mock_upstream


MOCK_UPSTREAM = mock_upstream()

# ── OpenTelemetry（P2-3 拆到 .otlp，re-export 保持向后兼容）──

# DB
STATS_FILE = settings.stats_file
DB_FILE = settings.db_file
IF_ROUTING_DB = settings.routing_db_file
IF_BASE64_DIR = settings.if_base64_dir
IF_BASE64_FILE_TTL = settings.if_base64_file_ttl
IF_IMG_MAX_GB = settings.if_img_max_gb
DB_RETENTION_DAYS = settings.db_retention_days
DB_CLEANUP_INTERVAL = settings.db_cleanup_interval
IF_TASK_RETENTION_DAYS = settings.if_task_retention_days
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

# ── CORS 白名单（模块级便捷引用，main.py 挂载 CORSMiddleware 时读取）──
# 必须取自 settings 而非字面量 "*"：拆包前 __init__.py 里 Settings.__init__ 的
# `global CORS_ORIGINS` 与本字面量同在 api.config 命名空间，字面量在后会覆盖 env 值
# （旧版即因此使 IF_CORS_ORIGINS 静默失效）；拆包后 global 写的是 settings_core
# 命名空间，更与本包无关。此处直接读单例，保证 env 生效。
CORS_ORIGINS = settings.if_cors_origins or "*"

# ── tryingopen.com 匿名网关（模块级便捷引用）────────────────
IF_TRYINGOPEN_ENABLED = settings.if_tryingopen_enabled
IF_TRYINGOPEN_HOURLY_PER_IP = settings.if_tryingopen_hourly_per_ip
IF_TRYINGOPEN_MAX_ATTEMPTS = settings.if_tryingopen_max_attempts
IF_TRYINGOPEN_SYNC_MINUTES = settings.if_tryingopen_sync_minutes

# ── P3-3 安全头开关（模块级便捷引用）────────────────
IF_SECURITY_HEADERS_ENABLED = settings.if_security_headers_enabled
IF_CSP_ENABLED = settings.if_csp_enabled
IF_DOCS_ENABLED = settings.if_docs_enabled
