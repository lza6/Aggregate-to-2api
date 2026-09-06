"""ProviderSettings 子配置。"""

from __future__ import annotations

from typing import Any

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

    @classmethod
    def from_settings(cls, s: Any) -> ProviderSettings:
        """从 Settings 实例提取字段构造 ProviderSettings。"""
        return cls(
            proxy_file=s.proxy_file,
            free_proxy_enabled=s.free_proxy_enabled,
            free_proxy_refresh_min=s.free_proxy_refresh_min,
            proxy_cooldown_seconds=s.proxy_cooldown_seconds,
            proxy_max_use_per_day=s.if_proxy_max_use_per_day,
            proxy_use_cooldown_map=s.if_proxy_use_cooldown_map,
            proxy_sticky_window=s.if_proxy_sticky_window,
            account_db_file=s.account_db_file,
            email_db_file=s.email_db_file,
            nanobanana_account_target=s.nanobanana_account_target,
            account_auto=s.account_auto,
            mock_register=s.mock_register,
            degrade_threshold=s.if_provider_degrade_threshold,
            recover_interval=s.if_provider_recover_interval,
            default_model=s.default_model,
            reg_backoff_cf=s.reg_backoff_cf,
            reg_backoff_email=s.reg_backoff_email,
            reg_backoff_ip=s.reg_backoff_ip,
            reg_backoff_transient_base=s.reg_backoff_transient_base,
            reg_backoff_transient_max=s.reg_backoff_transient_max,
            proxy_trace_enabled=s.if_proxy_trace_enabled,
            proxy_trace_ttl=s.if_proxy_trace_ttl,
            proxy_trace_max_per_round=s.if_proxy_trace_max_per_round,
            proxy_trace_concurrency=s.if_proxy_trace_concurrency,
            falai_enabled=s.if_falai_enabled,
            falai_hcaptcha_sitekey=s.if_falai_hcaptcha_sitekey,
            falai_hcaptcha_mode=s.if_falai_hcaptcha_mode,
            falai_browser_headful=s.if_falai_browser_headful,
            falai_browser_pool_size=s.if_falai_browser_pool_size,
            falai_verify_timeout=s.if_falai_verify_timeout,
            falai_poll_interval=s.if_falai_poll_interval,
            falai_poll_timeout=s.if_falai_poll_timeout,
        )
