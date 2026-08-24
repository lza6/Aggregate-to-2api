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
    account_db_file: str = "data/account_pool.db"
    email_db_file: str = "data/email_registry.db"
    minimaxh3_account_target: int = 500
    nanobanana_account_target: int = 500
    account_auto: bool = True
    mock_register: bool = False
    degrade_threshold: int = 3
    recover_interval: int = 300
    default_model: str = "default"