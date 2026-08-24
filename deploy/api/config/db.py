"""DBSettings 子配置。"""
from __future__ import annotations

from pydantic import BaseModel


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