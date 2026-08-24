"""CacheSettings 子配置。"""
from __future__ import annotations

from pydantic import BaseModel


class CacheSettings(BaseModel):
    """LRU 缓存配置组。"""

    size: int = 128
    ttl: int = 5