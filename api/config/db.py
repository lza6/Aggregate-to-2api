"""DBSettings 子配置。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DBSettings(BaseModel):
    """数据库配置组。"""

    file: str = "data/imagefree.db"
    stats_file: str = "data/stats.json"
    routing_db_file: str = ""  # P3-1: 路由决策持久化独立 sqlite；空 = 关闭
    retention_days: int = 365
    cleanup_interval: int = 21600
    batch_enabled: bool = True
    batch_window: float = 0.5
    pool_size: int = 5
    pool_timeout: int = 10
    base64_dir: str = "data/imgs"
    base64_file_ttl: int = 86400
    idempotency_enabled: bool = False
    idempotency_ttl: int = 900

    @classmethod
    def from_settings(cls, s: Any) -> DBSettings:
        """从 Settings 实例提取字段构造 DBSettings。"""
        return cls(
            file=s.db_file,
            stats_file=s.stats_file,
            retention_days=s.db_retention_days,
            cleanup_interval=s.db_cleanup_interval,
            batch_enabled=s.if_db_batch_enabled,
            batch_window=s.if_db_batch_window,
            pool_size=s.if_db_pool_size,
            pool_timeout=s.if_db_pool_timeout,
            base64_dir=s.if_base64_dir,
            base64_file_ttl=s.if_base64_file_ttl,
            idempotency_enabled=s.if_idempotency_enabled,
            idempotency_ttl=s.if_idempotency_ttl,
            routing_db_file=s.routing_db_file,
        )
