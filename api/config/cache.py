"""CacheSettings 子配置。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CacheSettings(BaseModel):
    """LRU 缓存配置组。"""

    size: int = 512
    ttl: int = 10
    redis_enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"

    @classmethod
    def from_settings(cls, s: Any) -> CacheSettings:
        """从 Settings 实例提取字段构造 CacheSettings。"""
        return cls(
            size=s.if_lru_cache_size,
            ttl=s.if_lru_cache_ttl,
            redis_enabled=s.if_redis_enabled,
            redis_url=s.if_redis_url,
        )
