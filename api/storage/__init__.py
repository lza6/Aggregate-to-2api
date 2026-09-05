"""存储适配层统一导出包。"""

from .base import DistributedLock, RateLimiter, StorageAdapter
from .factory import get_storage_adapter, set_storage_adapter
from .local import LocalStorageAdapter, MemoryRateLimiter, SQLiteLeaseLock
from .redis_adapter import RedisStorageAdapter  # noqa: F401  (lifespan P1-1 按需装配)

__all__ = [
    "DistributedLock",
    "RateLimiter",
    "StorageAdapter",
    "LocalStorageAdapter",
    "MemoryRateLimiter",
    "SQLiteLeaseLock",
    "RedisStorageAdapter",
    "get_storage_adapter",
    "set_storage_adapter",
]
