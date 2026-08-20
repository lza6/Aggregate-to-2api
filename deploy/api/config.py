"""imagefree_api 配置。全部可用环境变量覆盖，便于部署。

职责：pydantic-settings 集中管理全部 80+ 环境变量（IF_* 前缀）。
重构候选：967 行，可按功能拆分为 config/model、config/links、config/turnstile 等子模块，
但拆分风险高（模块级单例被全项目 import），当前仅记录不做拆分。
使用 pydantic-settings 集中管理配置，保持 IF_ 前缀环境变量向后兼容。
"""
from __future__ import annotations

import os

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── 子配置类（按功能分组）──────────────────────────────────


class DBSettings(BaseModel):
    """数据库配置组。"""

    file: str = "data/imagefree.db"
    stats_file: str = "data/stats.json"
    retention_days: int = 365
    cleanup_interval: int = 21600
    batch_enabled: bool = True
    batch_window: float = 0.2
    pool_size: int = 3
    pool_timeout: int = 5
    base64_dir: str = "data/imgs"
    base64_file_ttl: int = 86400
    idempotency_enabled: bool = False
    idempotency_ttl: int = 900


class HTTPSettings(BaseModel):
    """HTTP 连接配置组。"""

    host: str = "127.0.0.1"
    port: int = 8100
    proxy: str | None = None
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    )
    max_connections: int = 100
    keepalive: int = 20
    upstream_max_inflight: int = 30


class SolverSettings(BaseModel):
    """CF solver / Turnstile 求解配置组。"""

    base_url: str = "https://imagefree.net"
    sitekey: str = "0x4AAAAAACE-XLGoQUckKKm_"
    cf_solver_url: str = "http://127.0.0.1:8001"
    turnstile_timeout: int = 90
    turnstile_poll_interval: float = 2.0
    solve_circuit_threshold: int = 5
    solve_circuit_probe_seconds: int = 30
    solve_stats_window_seconds: int = 300
    healthz_cache_ttl: int = 5
    token_prefetch_concurrency: int = 1
    prefetch_after_solve_delay: float = 0.0
    prefetch_ema_alpha: float = 0.3


class CacheSettings(BaseModel):
    """LRU 缓存配置组。"""

    size: int = 128
    ttl: int = 5


class ProviderSettings(BaseModel):
    """多提供商 / 号池 / 邮箱池 / 代理池配置组。"""

    proxy_file: str = ""
    free_proxy_enabled: bool = False
    free_proxy_refresh_min: int = 30
    proxy_cooldown_seconds: int = 120
    proxy_max_use_per_day: int = 1
    proxy_use_cooldown_map: str = "0,30,90,300,900"
    account_db_file: str = "data/account_pool.db"
    email_db_file: str = "data/email_registry.db"
    minimaxh3_account_target: int = 500
    nanobanana_account_target: int = 500
    account_auto: bool = True
    mock_register: bool = False
    degrade_threshold: int = 3
    recover_interval: int = 300
    default_model: str = "default"


class PoolSettings(BaseModel):
    """Token 池配置组。"""

    token_pool_size: int = 6
    token_ttl: int = 90
    token_wait_timeout: int = 30


class QueueSettings(BaseModel):
    """队列 / Worker 配置组。"""

    max_queue: int = 2000
    admin_queue_max: int = 200
    high_queue_max: int = 500
    normal_queue_max: int = 1500
    workers: int = 10
    worker_auto: bool = False
    workers_min: int = 4
    workers_max: int = 16
    worker_scale_up_threshold: int = 200
    worker_scale_down_threshold: int = 20
    worker_idle_seconds: int = 90
    persistent_queue_enabled: bool = False
    persistent_queue_db: str = "data/queue.db"
    dlq_enabled: bool = True
    dlq_max_retries: int = 3
    dlq_retention_days: int = 7


class ObservabilitySettings(BaseModel):
    """可观测性 / 治理配置组。"""

    health_check_interval: int = 60
    health_check_enabled: bool = True
    alert_check_interval: int = 60


class EditSettings(BaseModel):
    """图生图编辑配置组。"""

    edit_timeout: int = 3600
    task_hard_timeout: int = 480
    edit_concurrency_wait: int = 60
    edit_mutex_enabled: bool = True
    edit_lock_max_age: int = 1500
    edit_retry_max: int = 30
    edit_retry_interval: int = 20
    edit_proxy_file: str = ""
    edit_proxy_parallel: int = 1
    edit_proxy_max_inflight: int = 2
    edit_proxy_pool_size: int = 1
    edit_proxy_pool_idle_ttl: int = 180
    generate_timeout: int = 300
    generate_poll_interval: float = 2.0
    generate_max_attempts: int = 2
    txt_retry_max: int = 3
    txt_retry_backoff_base: int = 5
    sync_timeout: int = 300
    max_image_bytes: int = 4 * 1024 * 1024


class SecuritySettings(BaseModel):
    """安全 / 鉴权配置组。"""

    gallery_password: str = ""


# ── 顶层 Settings 类 ──────────────────────────────────────


class Settings(BaseSettings):
    """imagefree-api 全局配置。

    所有环境变量使用 IF_ 前缀。通过 validation_alias 映射到字段名。
    子配置类通过属性访问（如 settings.db.file）。
    """

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    # ── Solver ──
    base_url: str = Field(
        "https://imagefree.net", validation_alias="IF_BASE_URL"
    )
    sitekey: str = Field(
        "0x4AAAAAACE-XLGoQUckKKm_", validation_alias="IF_SITEKEY"
    )
    cf_solver_url: str = Field(
        "http://127.0.0.1:8001", validation_alias="IF_CF_SOLVER_URL"
    )

    # ── HTTP ──
    host: str = Field("127.0.0.1", validation_alias="IF_HOST")
    port: int = Field(8100, validation_alias="IF_PORT")
    proxy: str | None = Field(
        default=None, validation_alias="IF_PROXY"
    )
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    )
    if_http_max_connections: int = Field(
        100, validation_alias="IF_HTTP_MAX_CONNECTIONS"
    )
    if_http_keepalive: int = Field(20, validation_alias="IF_HTTP_KEEPALIVE")
    if_upstream_max_inflight: int = Field(
        30, validation_alias="IF_UPSTREAM_MAX_INFLIGHT"
    )

    # ── Turnstile / Solver ──
    turnstile_timeout: int = Field(
        90, validation_alias="IF_TURNSTILE_TIMEOUT"
    )
    turnstile_poll_interval: float = Field(
        2.0, validation_alias="IF_TURNSTILE_POLL_INTERVAL"
    )
    healthz_cache_ttl: int = Field(
        5, validation_alias="IF_HEALTHZ_CACHE_TTL"
    )
    token_prefetch_concurrency: int = Field(
        1, validation_alias="IF_TOKEN_PREFETCH_CONCURRENCY"
    )
    if_prefetch_after_solve_delay: float = Field(
        0.0, validation_alias="IF_PREFETCH_AFTER_SOLVE_DELAY"
    )
    if_prefetch_ema_alpha: float = Field(
        0.3, validation_alias="IF_PREFETCH_EMA_ALPHA"
    )
    solve_circuit_threshold: int = Field(
        5, validation_alias="IF_SOLVE_CIRCUIT_THRESHOLD"
    )
    solve_circuit_probe_seconds: int = Field(
        30, validation_alias="IF_SOLVE_CIRCUIT_PROBE_SECONDS"
    )
    solve_stats_window_seconds: int = Field(
        300, validation_alias="IF_SOLVE_STATS_WINDOW_SECONDS"
    )

    # ── 超时 / 轮询 ──
    generate_timeout: int = Field(300, validation_alias="IF_GENERATE_TIMEOUT")
    generate_poll_interval: float = Field(
        2.0, validation_alias="IF_GENERATE_POLL_INTERVAL"
    )
    edit_timeout: int = Field(3600, validation_alias="IF_EDIT_TIMEOUT")
    task_hard_timeout: int = Field(
        480, validation_alias="IF_TASK_HARD_TIMEOUT"
    )
    edit_concurrency_wait: int = Field(
        60, validation_alias="IF_EDIT_CONCURRENCY_WAIT"
    )
    edit_mutex_enabled: bool = Field(
        True, validation_alias="IF_EDIT_MUTEX_ENABLED"
    )
    edit_lock_max_age: int = Field(
        1500, validation_alias="IF_EDIT_LOCK_MAX_AGE"
    )
    edit_retry_max: int = Field(30, validation_alias="IF_EDIT_RETRY_MAX")
    edit_retry_interval: int = Field(
        20, validation_alias="IF_EDIT_RETRY_INTERVAL"
    )
    edit_proxy_file: str = Field(
        "", validation_alias="IF_EDIT_PROXY_FILE"
    )
    edit_proxy_parallel: int = Field(
        1, validation_alias="IF_EDIT_PROXY_PARALLEL"
    )
    if_edit_proxy_max_inflight: int = Field(
        2, validation_alias="IF_EDIT_PROXY_MAX_INFLIGHT"
    )
    edit_proxy_pool_size: int = Field(
        1, validation_alias="IF_EDIT_PROXY_POOL_SIZE"
    )
    edit_proxy_pool_idle_ttl: int = Field(
        180, validation_alias="IF_EDIT_PROXY_POOL_IDLE_TTL"
    )
    generate_max_attempts: int = Field(
        2, validation_alias="IF_GENERATE_MAX_ATTEMPTS"
    )
    if_txt_retry_max: int = Field(
        3, validation_alias="IF_TXT_RETRY_MAX"
    )
    if_txt_retry_backoff_base: int = Field(
        5, validation_alias="IF_TXT_RETRY_BACKOFF_BASE"
    )
    token_wait_timeout: int = Field(
        30, validation_alias="IF_TOKEN_WAIT_TIMEOUT"
    )
    sync_timeout: int = Field(300, validation_alias="IF_SYNC_TIMEOUT")

    # ── 队列 / Worker ──
    max_queue: int = Field(2000, validation_alias="IF_MAX_QUEUE")
    admin_queue_max: int = Field(200, validation_alias="IF_ADMIN_QUEUE_MAX")
    high_queue_max: int = Field(500, validation_alias="IF_HIGH_QUEUE_MAX")
    normal_queue_max: int = Field(
        1500, validation_alias="IF_NORMAL_QUEUE_MAX"
    )
    workers: int = Field(10, validation_alias="IF_WORKERS")
    if_worker_auto: bool = Field(False, validation_alias="IF_WORKER_AUTO")
    if_workers_min: int = Field(4, validation_alias="IF_WORKERS_MIN")
    if_workers_max: int = Field(16, validation_alias="IF_WORKERS_MAX")
    if_worker_scale_up_threshold: int = Field(
        200, validation_alias="IF_WORKER_SCALE_UP_THRESHOLD"
    )
    if_worker_scale_down_threshold: int = Field(
        20, validation_alias="IF_WORKER_SCALE_DOWN_THRESHOLD"
    )
    if_worker_idle_seconds: int = Field(
        90, validation_alias="IF_WORKER_IDLE_SECONDS"
    )
    if_persistent_queue_enabled: bool = Field(
        False, validation_alias="IF_PERSISTENT_QUEUE_ENABLED"
    )
    if_persistent_queue_db: str = Field(
        "data/queue.db", validation_alias="IF_PERSISTENT_QUEUE_DB"
    )
    # worker 批量调度（可选优化）：启用后 worker 按小批次消费队列减少上下文切换
    if_worker_batch_enabled: bool = Field(
        False, validation_alias="IF_WORKER_BATCH_ENABLED"
    )
    if_worker_batch_size: int = Field(5, validation_alias="IF_WORKER_BATCH_SIZE")

    # ── Token 池 ──
    token_pool_size: int = Field(6, validation_alias="IF_TOKEN_POOL_SIZE")
    token_ttl: int = Field(90, validation_alias="IF_TOKEN_TTL")

    # ── 画廊 ──
    gallery_limit: int = Field(50, validation_alias="IF_GALLERY_LIMIT")
    if_gallery_password: str = Field(
        "", validation_alias="IF_GALLERY_PASSWORD"
    )

    # ── 缓存 ──
    if_lru_cache_size: int = Field(
        128, validation_alias="IF_LRU_CACHE_SIZE"
    )
    if_lru_cache_ttl: int = Field(
        5, validation_alias="IF_LRU_CACHE_TTL"
    )

    # ── 可观测性 ──
    if_health_check_interval: int = Field(
        60, validation_alias="IF_HEALTH_CHECK_INTERVAL"
    )
    if_health_check_enabled: bool = Field(
        True, validation_alias="IF_HEALTH_CHECK_ENABLED"
    )
    if_alert_check_interval: int = Field(
        60, validation_alias="IF_ALERT_CHECK_INTERVAL"
    )

    # ── DB ──
    stats_file: str = Field(
        "data/stats.json", validation_alias="IF_STATS_FILE"
    )
    db_file: str = Field(
        "data/imagefree.db", validation_alias="IF_DB_FILE"
    )
    if_base64_dir: str = Field(
        "data/imgs", validation_alias="IF_BASE64_DIR"
    )
    if_base64_file_ttl: int = Field(
        86400, validation_alias="IF_BASE64_FILE_TTL"
    )
    db_retention_days: int = Field(
        365, validation_alias="IF_DB_RETENTION_DAYS"
    )
    db_cleanup_interval: int = Field(
        21600, validation_alias="IF_DB_CLEANUP_INTERVAL"
    )
    if_db_batch_enabled: bool = Field(
        True, validation_alias="IF_DB_BATCH_ENABLED"
    )
    if_db_batch_window: float = Field(
        0.2, validation_alias="IF_DB_BATCH_WINDOW"
    )
    if_db_pool_size: int = Field(3, validation_alias="IF_DB_POOL_SIZE")
    if_db_pool_timeout: int = Field(
        5, validation_alias="IF_DB_POOL_TIMEOUT"
    )

    # ── Provider / 代理池 / 号池 ──
    proxy_file: str = Field("", validation_alias="IF_PROXY_FILE")
    free_proxy_enabled: bool = Field(
        False, validation_alias="IF_FREE_PROXY"
    )
    free_proxy_refresh_min: int = Field(
        30, validation_alias="IF_FREE_PROXY_REFRESH_MIN"
    )
    proxy_cooldown_seconds: int = Field(
        120, validation_alias="IF_PROXY_COOLDOWN_SECONDS"
    )
    if_proxy_max_use_per_day: int = Field(
        1, validation_alias="IF_PROXY_MAX_USE_PER_DAY"
    )
    if_proxy_use_cooldown_map: str = Field(
        "0,30,90,300,900", validation_alias="IF_PROXY_USE_COOLDOWN_MAP"
    )
    account_db_file: str = Field(
        "data/account_pool.db", validation_alias="IF_ACCOUNT_DB_FILE"
    )
    email_db_file: str = Field(
        "data/email_registry.db", validation_alias="IF_EMAIL_DB_FILE"
    )
    minimaxh3_account_target: int = Field(
        500, validation_alias="IF_MINIMAXH3_ACCOUNT_TARGET"
    )
    nanobanana_account_target: int = Field(
        500, validation_alias="IF_NANOBANANA_ACCOUNT_TARGET"
    )
    account_auto: bool = Field(True, validation_alias="IF_ACCOUNT_AUTO")
    mock_register: bool = Field(
        False, validation_alias="IF_MOCK_REGISTER"
    )
    if_provider_degrade_threshold: int = Field(
        3, validation_alias="IF_PROVIDER_DEGRADE_THRESHOLD"
    )
    if_provider_recover_interval: int = Field(
        300, validation_alias="IF_PROVIDER_RECOVER_INTERVAL"
    )
    if_idempotency_enabled: bool = Field(
        False, validation_alias="IF_IDEMPOTENCY_ENABLED"
    )
    if_idempotency_ttl: int = Field(
        900, validation_alias="IF_IDEMPOTENCY_TTL"
    )
    if_dlq_enabled: bool = Field(True, validation_alias="IF_DLQ_ENABLED")
    if_dlq_max_retries: int = Field(
        3, validation_alias="IF_DLQ_MAX_RETRIES"
    )
    if_dlq_retention_days: int = Field(
        7, validation_alias="IF_DLQ_RETENTION_DAYS"
    )
    default_model: str = Field(
        "default", validation_alias="IF_DEFAULT_MODEL"
    )

    # ── 分组配置（延迟初始化，由 model_validator 填充）───────────────
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
        "if_worker_auto",
        "if_persistent_queue_enabled",
        "if_health_check_enabled",
        "if_db_batch_enabled",
        "free_proxy_enabled",
        "account_auto",
        "mock_register",
        "if_idempotency_enabled",
        "if_dlq_enabled",
        mode="before",
    )
    @classmethod
    def _bool_str_coerce(cls, v: str | bool) -> bool:
        """'1'/'true'/'yes'/'on' → True 的字符串兼容。"""
        if isinstance(v, bool):
            return v
        return v.strip().lower() in {"1", "true", "yes", "on"}

    @model_validator(mode="after")
    def _resolve_proxy_and_init_groups(self) -> "Settings":
        """代理 fallback 解析 + 分组配置初始化。"""
        # ── 代理 fallback ──
        if not self.proxy:
            for var in ("HTTPS_PROXY", "HTTP_PROXY"):
                val = os.environ.get(var)
                if val:
                    self.proxy = val
                    break

        # ── 分组配置 ──
        self._db = DBSettings(
            file=self.db_file,
            stats_file=self.stats_file,
            retention_days=self.db_retention_days,
            cleanup_interval=self.db_cleanup_interval,
            batch_enabled=self.if_db_batch_enabled,
            batch_window=self.if_db_batch_window,
            pool_size=self.if_db_pool_size,
            pool_timeout=self.if_db_pool_timeout,
            base64_dir=self.if_base64_dir,
            base64_file_ttl=self.if_base64_file_ttl,
            idempotency_enabled=self.if_idempotency_enabled,
            idempotency_ttl=self.if_idempotency_ttl,
        )
        self._http = HTTPSettings(
            host=self.host,
            port=self.port,
            proxy=self.proxy,
            user_agent=self.user_agent,
            max_connections=self.if_http_max_connections,
            keepalive=self.if_http_keepalive,
            upstream_max_inflight=self.if_upstream_max_inflight,
        )
        self._solver = SolverSettings(
            base_url=self.base_url,
            sitekey=self.sitekey,
            cf_solver_url=self.cf_solver_url,
            turnstile_timeout=self.turnstile_timeout,
            turnstile_poll_interval=self.turnstile_poll_interval,
            solve_circuit_threshold=self.solve_circuit_threshold,
            solve_circuit_probe_seconds=self.solve_circuit_probe_seconds,
            solve_stats_window_seconds=self.solve_stats_window_seconds,
            healthz_cache_ttl=self.healthz_cache_ttl,
            token_prefetch_concurrency=self.token_prefetch_concurrency,
            prefetch_after_solve_delay=self.if_prefetch_after_solve_delay,
            prefetch_ema_alpha=self.if_prefetch_ema_alpha,
        )
        self._cache = CacheSettings(
            size=self.if_lru_cache_size,
            ttl=self.if_lru_cache_ttl,
        )
        self._provider = ProviderSettings(
            proxy_file=self.proxy_file,
            free_proxy_enabled=self.free_proxy_enabled,
            free_proxy_refresh_min=self.free_proxy_refresh_min,
            proxy_cooldown_seconds=self.proxy_cooldown_seconds,
            proxy_max_use_per_day=self.if_proxy_max_use_per_day,
            proxy_use_cooldown_map=self.if_proxy_use_cooldown_map,
            account_db_file=self.account_db_file,
            email_db_file=self.email_db_file,
            minimaxh3_account_target=self.minimaxh3_account_target,
            nanobanana_account_target=self.nanobanana_account_target,
            account_auto=self.account_auto,
            mock_register=self.mock_register,
            degrade_threshold=self.if_provider_degrade_threshold,
            recover_interval=self.if_provider_recover_interval,
            default_model=self.default_model,
        )
        self._pool = PoolSettings(
            token_pool_size=self.token_pool_size,
            token_ttl=self.token_ttl,
            token_wait_timeout=self.token_wait_timeout,
        )
        self._queue = QueueSettings(
            max_queue=self.max_queue,
            admin_queue_max=self.admin_queue_max,
            high_queue_max=self.high_queue_max,
            normal_queue_max=self.normal_queue_max,
            workers=self.workers,
            worker_auto=self.if_worker_auto,
            workers_min=self.if_workers_min,
            workers_max=self.if_workers_max,
            worker_scale_up_threshold=self.if_worker_scale_up_threshold,
            worker_scale_down_threshold=self.if_worker_scale_down_threshold,
            worker_idle_seconds=self.if_worker_idle_seconds,
            persistent_queue_enabled=self.if_persistent_queue_enabled,
            persistent_queue_db=self.if_persistent_queue_db,
            dlq_enabled=self.if_dlq_enabled,
            dlq_max_retries=self.if_dlq_max_retries,
            dlq_retention_days=self.if_dlq_retention_days,
        )
        self._observability = ObservabilitySettings(
            health_check_interval=self.if_health_check_interval,
            health_check_enabled=self.if_health_check_enabled,
            alert_check_interval=self.if_alert_check_interval,
        )
        self._edit = EditSettings(
            edit_timeout=self.edit_timeout,
            task_hard_timeout=self.task_hard_timeout,
            edit_concurrency_wait=self.edit_concurrency_wait,
            edit_mutex_enabled=self.edit_mutex_enabled,
            edit_lock_max_age=self.edit_lock_max_age,
            edit_retry_max=self.edit_retry_max,
            edit_retry_interval=self.edit_retry_interval,
            edit_proxy_file=self.edit_proxy_file,
            edit_proxy_parallel=self.edit_proxy_parallel,
            edit_proxy_max_inflight=self.if_edit_proxy_max_inflight,
            edit_proxy_pool_size=self.edit_proxy_pool_size,
            edit_proxy_pool_idle_ttl=self.edit_proxy_pool_idle_ttl,
            generate_timeout=self.generate_timeout,
            generate_poll_interval=self.generate_poll_interval,
            generate_max_attempts=self.generate_max_attempts,
            txt_retry_max=self.if_txt_retry_max,
            txt_retry_backoff_base=self.if_txt_retry_backoff_base,
            sync_timeout=self.sync_timeout,
            max_image_bytes=4 * 1024 * 1024,
        )
        self._security = SecuritySettings(
            gallery_password=self.if_gallery_password,
        )
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
        """导出完整配置快照（供 /v1/meta 扩展）。"""
        return {
            "db": self.db.model_dump(),
            "http": self.http.model_dump(),
            "solver": self.solver.model_dump(),
            "cache": self.cache.model_dump(),
            "provider": self.provider.model_dump(),
            "pool": self.pool.model_dump(),
            "queue": self.queue.model_dump(),
            "observability": self.observability.model_dump(),
            "edit": self.edit.model_dump(),
            "security": self.security.model_dump(),
        }

    def validate(self) -> list[str]:
        """启动时校验关键配置，返回错误列表。"""
        errors: list[str] = []
        if not self.base_url:
            errors.append("BASE_URL（IF_BASE_URL）不能为空")
        if not self.sitekey:
            errors.append("SITEKEY（IF_SITEKEY）不能为空")
        if not self.cf_solver_url:
            errors.append("CF_SOLVER_URL（IF_CF_SOLVER_URL）不能为空")
        if self.port < 1 or self.port > 65535:
            errors.append(
                f"PORT（IF_PORT）={self.port} 超出有效范围 1-65535"
            )
        if self.max_queue < 1:
            errors.append(
                f"MAX_QUEUE（IF_MAX_QUEUE）={self.max_queue} 必须 >= 1"
            )
        if self.workers < 1:
            errors.append(
                f"WORKERS（IF_WORKERS）={self.workers} 必须 >= 1"
            )
        if self.token_pool_size < 1:
            errors.append(
                f"TOKEN_POOL_SIZE（IF_TOKEN_POOL_SIZE）={self.token_pool_size} 必须 >= 1"
            )
        if self.if_workers_max < self.if_workers_min:
            errors.append(
                f"IF_WORKERS_MAX（{self.if_workers_max}）"
                f" < IF_WORKERS_MIN（{self.if_workers_min}）"
            )
        return errors


# ── 模块级单例 ──────────────────────────────────────────
settings = Settings()


# ── 模块级变量（保持向后兼容）───────────────────────────────
# Solver
BASE_URL = settings.base_url
SITEKEY = settings.sitekey
CF_SOLVER_URL = settings.cf_solver_url

# HTTP
HOST = settings.host
PORT = settings.port
PROXY = settings.proxy
USER_AGENT = settings.user_agent
IF_HTTP_MAX_CONNECTIONS = settings.if_http_max_connections
IF_HTTP_KEEPALIVE = settings.if_http_keepalive
IF_UPSTREAM_MAX_INFLIGHT = settings.if_upstream_max_inflight

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
IF_PERSISTENT_QUEUE_ENABLED = settings.if_persistent_queue_enabled
IF_PERSISTENT_QUEUE_DB = settings.if_persistent_queue_db
IF_WORKER_BATCH_ENABLED = settings.if_worker_batch_enabled
IF_WORKER_BATCH_SIZE = settings.if_worker_batch_size

# Token 池
TOKEN_POOL_SIZE = settings.token_pool_size
TOKEN_TTL = settings.token_ttl

# 画廊
GALLERY_LIMIT = settings.gallery_limit
IF_GALLERY_PASSWORD = settings.if_gallery_password

# 缓存
IF_LRU_CACHE_SIZE = settings.if_lru_cache_size
IF_LRU_CACHE_TTL = settings.if_lru_cache_ttl

# 可观测性
IF_HEALTH_CHECK_INTERVAL = settings.if_health_check_interval
IF_HEALTH_CHECK_ENABLED = settings.if_health_check_enabled
IF_ALERT_CHECK_INTERVAL = settings.if_alert_check_interval

# ── mock 上游开关（E2E/CI；生产留空）──────────────
MOCK_UPSTREAM = os.getenv("IF_MOCK_UPSTREAM", "0").strip().lower() in {"1", "true", "yes", "on"}

# ── OpenTelemetry（IF_OTEL_*）───────────────────
OTEL_ENABLED = os.getenv("IF_OTEL_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
OTEL_SERVICE_NAME = os.getenv("IF_OTEL_SERVICE_NAME", "imagefree-api")
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("IF_OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
OTEL_CONSOLE_EXPORTER = os.getenv("IF_OTEL_CONSOLE_EXPORTER", "0").strip().lower() in {"1", "true", "yes", "on"}

# DB
STATS_FILE = settings.stats_file
DB_FILE = settings.db_file
IF_BASE64_DIR = settings.if_base64_dir
IF_BASE64_FILE_TTL = settings.if_base64_file_ttl
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
ACCOUNT_DB_FILE = settings.account_db_file
EMAIL_DB_FILE = settings.email_db_file
MINIMAXH3_ACCOUNT_TARGET = settings.minimaxh3_account_target
NANOBANANA_ACCOUNT_TARGET = settings.nanobanana_account_target
ACCOUNT_AUTO = settings.account_auto
MOCK_REGISTER = settings.mock_register
IF_PROVIDER_DEGRADE_THRESHOLD = settings.if_provider_degrade_threshold
IF_PROVIDER_RECOVER_INTERVAL = settings.if_provider_recover_interval
IF_IDEMPOTENCY_ENABLED = settings.if_idempotency_enabled
IF_IDEMPOTENCY_TTL = settings.if_idempotency_ttl
IF_DLQ_ENABLED = settings.if_dlq_enabled
IF_DLQ_MAX_RETRIES = settings.if_dlq_max_retries
IF_DLQ_RETENTION_DAYS = settings.if_dlq_retention_days
DEFAULT_MODEL = settings.default_model

# ── 纯常量（无环境变量映射）────────────────────────────────
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_PROMPT_LEN = 2000

ASPECT_RATIOS: dict[str, str] = {
    "1:1": "1024x1024",
    "3:4": "768x1024",
    "4:3": "1024x768",
    "9:16": "576x1024",
    "16:9": "1024x576",
}

MODEL_PRESETS: dict[str, dict] = {
    "default": {
        "name": "默认",
        "description": "不注入任何风格，原样提交提示词",
        "prefix": "",
        "applies_to": ["txt2img", "img2img"],
    },
    "anime": {
        "name": "动漫",
        "description": "日系动漫插画风格，高完成度线稿与上色",
        "prefix": "anime style, high quality anime illustration, vibrant colors, detailed lineart, ",
        "applies_to": ["txt2img"],
    },
    "realistic": {
        "name": "写实摄影",
        "description": "超写实照片质感，高细节、电影级光影",
        "prefix": "photorealistic, ultra detailed, 8k, cinematic lighting, sharp focus, ",
        "applies_to": ["txt2img"],
    },
    "watercolor": {
        "name": "水彩",
        "description": "水彩画风格，柔和晕染、通透层次",
        "prefix": "watercolor painting style, soft washes, delicate brushwork, translucent layers, ",
        "applies_to": ["txt2img", "img2img"],
    },
    "ink": {
        "name": "水墨",
        "description": "中国传统水墨画风，留白、写意、淡雅",
        "prefix": "traditional chinese ink wash painting style, minimalist, elegant negative space, ",
        "applies_to": ["txt2img"],
    },
    "cyberpunk": {
        "name": "赛博朋克",
        "description": "赛博朋克霓虹风格，未来都市、强对比色调",
        "prefix": "cyberpunk neon style, futuristic city, neon glow, high contrast, ",
        "applies_to": ["txt2img", "img2img"],
    },
}


def apply_model(prompt: str, model: str) -> str:
    """模型风格预设 → prompt 前缀注入（default 不加前缀）。供 worker/main 共用。"""
    prefix = MODEL_PRESETS.get(model, {}).get("prefix", "")
    return prefix + prompt if prefix else prompt


# ── 导出所有模块级变量名 ──────────────────────────────────
__all__ = [
    "DBSettings",
    "HTTPSettings",
    "SolverSettings",
    "CacheSettings",
    "ProviderSettings",
    "PoolSettings",
    "QueueSettings",
    "ObservabilitySettings",
    "EditSettings",
    "SecuritySettings",
    "Settings",
    "settings",
    "BASE_URL",
    "SITEKEY",
    "CF_SOLVER_URL",
    "HOST",
    "PORT",
    "PROXY",
    "USER_AGENT",
    "IF_HTTP_MAX_CONNECTIONS",
    "IF_HTTP_KEEPALIVE",
    "IF_UPSTREAM_MAX_INFLIGHT",
    "TURNSTILE_TIMEOUT",
    "TURNSTILE_POLL_INTERVAL",
    "HEALTHZ_CACHE_TTL",
    "TOKEN_PREFETCH_CONCURRENCY",
    "IF_PREFETCH_AFTER_SOLVE_DELAY",
    "IF_PREFETCH_EMA_ALPHA",
    "SOLVE_CIRCUIT_THRESHOLD",
    "SOLVE_CIRCUIT_PROBE_SECONDS",
    "SOLVE_STATS_WINDOW_SECONDS",
    "GENERATE_TIMEOUT",
    "GENERATE_POLL_INTERVAL",
    "EDIT_TIMEOUT",
    "TASK_HARD_TIMEOUT",
    "EDIT_CONCURRENCY_WAIT",
    "EDIT_MUTEX_ENABLED",
    "EDIT_LOCK_MAX_AGE",
    "EDIT_RETRY_MAX",
    "EDIT_RETRY_INTERVAL",
    "EDIT_PROXY_FILE",
    "EDIT_PROXY_PARALLEL",
    "IF_EDIT_PROXY_MAX_INFLIGHT",
    "EDIT_PROXY_POOL_SIZE",
    "EDIT_PROXY_POOL_IDLE_TTL",
    "GENERATE_MAX_ATTEMPTS",
    "IF_TXT_RETRY_MAX",
    "IF_TXT_RETRY_BACKOFF_BASE",
    "TOKEN_WAIT_TIMEOUT",
    "SYNC_TIMEOUT",
    "MAX_QUEUE",
    "ADMIN_QUEUE_MAX",
    "HIGH_QUEUE_MAX",
    "NORMAL_QUEUE_MAX",
    "WORKERS",
    "IF_WORKER_AUTO",
    "IF_WORKERS_MIN",
    "IF_WORKERS_MAX",
    "IF_WORKER_SCALE_UP_THRESHOLD",
    "IF_WORKER_SCALE_DOWN_THRESHOLD",
    "IF_WORKER_IDLE_SECONDS",
    "IF_PERSISTENT_QUEUE_ENABLED",
    "IF_PERSISTENT_QUEUE_DB",
    "TOKEN_POOL_SIZE",
    "TOKEN_TTL",
    "GALLERY_LIMIT",
    "IF_GALLERY_PASSWORD",
    "IF_LRU_CACHE_SIZE",
    "IF_LRU_CACHE_TTL",
    "IF_HEALTH_CHECK_INTERVAL",
    "IF_HEALTH_CHECK_ENABLED",
    "IF_ALERT_CHECK_INTERVAL",
    "MOCK_UPSTREAM",
    "OTEL_ENABLED",
    "OTEL_SERVICE_NAME",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_CONSOLE_EXPORTER",
    "STATS_FILE",
    "DB_FILE",
    "IF_BASE64_DIR",
    "IF_BASE64_FILE_TTL",
    "DB_RETENTION_DAYS",
    "DB_CLEANUP_INTERVAL",
    "IF_DB_BATCH_ENABLED",
    "IF_DB_BATCH_WINDOW",
    "IF_DB_POOL_SIZE",
    "IF_DB_POOL_TIMEOUT",
    "PROXY_FILE",
    "FREE_PROXY_ENABLED",
    "FREE_PROXY_REFRESH_MIN",
    "PROXY_COOLDOWN_SECONDS",
    "IF_PROXY_MAX_USE_PER_DAY",
    "IF_PROXY_USE_COOLDOWN_MAP",
    "ACCOUNT_DB_FILE",
    "EMAIL_DB_FILE",
    "MINIMAXH3_ACCOUNT_TARGET",
    "NANOBANANA_ACCOUNT_TARGET",
    "ACCOUNT_AUTO",
    "MOCK_REGISTER",
    "IF_PROVIDER_DEGRADE_THRESHOLD",
    "IF_PROVIDER_RECOVER_INTERVAL",
    "IF_IDEMPOTENCY_ENABLED",
    "IF_IDEMPOTENCY_TTL",
    "IF_DLQ_ENABLED",
    "IF_DLQ_MAX_RETRIES",
    "IF_DLQ_RETENTION_DAYS",
    "DEFAULT_MODEL",
    "MAX_IMAGE_BYTES",
    "MAX_PROMPT_LEN",
    "ASPECT_RATIOS",
    "MODEL_PRESETS",
    "apply_model",
]