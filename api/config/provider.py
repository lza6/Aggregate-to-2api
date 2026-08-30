"""ProviderSettings 子配置。"""

from __future__ import annotations

from pydantic import BaseModel


class ProviderSettings(BaseModel):
    """多提供商 / 号池 / 邮箱池 / 代理池配置组。"""

    proxy_file: str = ""
    free_proxy_enabled: bool = False
    free_proxy_refresh_min: int = 30
    proxy_cooldown_seconds: int = 120
    proxy_max_use_per_day: int = 1
    proxy_use_cooldown_map: str = "0,30,90,300,900"
    # Cloudflare trace 出口探测器（v6.7.x）
    proxy_trace_enabled: bool = False
    proxy_trace_ttl: int = 3600
    proxy_trace_max_per_round: int = 50
    proxy_trace_concurrency: int = 8
    account_db_file: str = "data/account_pool.db"
    email_db_file: str = "data/email_registry.db"
    nanobanana_account_target: int = 10000
    account_auto: bool = True
    mock_register: bool = False
    degrade_threshold: int = 3
    recover_interval: int = 300
    default_model: str = "default"
    # 自适应注册退避配置
    reg_backoff_cf: float = 30.0
    reg_backoff_email: float = 60.0
    reg_backoff_ip: float = 120.0
    reg_backoff_transient_base: float = 2.0
    reg_backoff_transient_max: float = 30.0
    # fal.ai minimax-H3 视频提供商（Playwright 浏览器即服务）
    falai_enabled: bool = True
    falai_hcaptcha_sitekey: str = "79e0463a-f79a-4742-b3da-489afd1cbe68"
    falai_hcaptcha_mode: str = "passive"
    falai_browser_headful: bool = True
    falai_browser_pool_size: int = 2
    falai_verify_timeout: int = 90
    falai_poll_interval: float = 2.0
    falai_poll_timeout: int = 120
