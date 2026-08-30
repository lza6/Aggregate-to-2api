"""CacheSettings 子配置。"""

from __future__ import annotations

from pydantic import BaseModel


class CacheSettings(BaseModel):
    """LRU 缓存配置组。"""

    size: int = 512
    ttl: int = 10
    redis_enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"
