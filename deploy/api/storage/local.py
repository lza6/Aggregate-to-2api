"""单机内存与 SQLite 存储适配实现（Zero-External-Dependency 模式）。"""
from __future__ import annotations

import asyncio
import collections
import logging
import os
import time
import uuid

from .base import DistributedLock, RateLimiter, StorageAdapter

log = logging.getLogger("storage.memory")


class MemoryRateLimiter(RateLimiter):
    """基于内存滑动窗口双端队列的限流实现。"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._requests: dict[str, collections.deque[float]] = {}

    async def is_allowed(self, key: str, limit: int, window: float = 60.0) -> bool:
        if limit <= 0:
            return True
        now = time.monotonic()
        async with self._lock:
            bucket = self._requests.setdefault(key, collections.deque())
            while bucket and now - bucket[0] >= window:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            # 防止长期运行 key 无限膨胀
            if len(self._requests) > 10000:
                expired = [k for k, v in self._requests.items() if not v or now - v[-1] >= window]
                for k in expired:
                    self._requests.pop(k, None)
            return True

    async def get_count(self, key: str, window: float = 60.0) -> int:
        now = time.monotonic()
        async with self._lock:
            bucket = self._requests.get(key)
            if not bucket:
                return 0
            while bucket and now - bucket[0] >= window:
                bucket.popleft()
            return len(bucket)

    async def reset(self, key: str) -> None:
        async with self._lock:
            self._requests.pop(key, None)


class SQLiteLeaseLock(DistributedLock):
    """基于 SQLite LeaseStore 的分布式/跨进程租约锁（沿用 dispatch_edit 的租约语义）。"""

    def __init__(self, lease_store=None, db_path: str | None = None) -> None:
        self._store = lease_store
        self._db_path = db_path

    def _get_store(self):
        if self._store is None:
            from .. import config
            from ..db.lease_store import LeaseStore
            path = self._db_path or os.path.join(os.path.dirname(config.DB_FILE) or ".", "edit_leases.db")
            self._store = LeaseStore(path)
        return self._store

    async def acquire(self, key: str, holder: str, ttl: float = 60.0, timeout: float | None = None) -> str | None:
        store = self._get_store()
        token = uuid.uuid4().hex
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            if deadline is not None and time.monotonic() > deadline:
                return None
            try:
                ok = await store.acquire(key, holder, token, ttl)
                if ok:
                    return token
            except Exception as e:
                log.warning("SQLiteLeaseLock acquire 失败: %s", e)
            await asyncio.sleep(0.5)

    async def release(self, key: str, token: str | None) -> bool:
        if not token:
            return False
        store = self._get_store()
        try:
            return await store.release(key, token)
        except Exception as e:
            log.warning("SQLiteLeaseLock release 失败: %s", e)
            return False


class LocalStorageAdapter(StorageAdapter):
    """默认单机适配器（无需外部 Redis，内存限流 + SQLite Lease 锁）。"""

    def __init__(self) -> None:
        self._lock = SQLiteLeaseLock()
        self._rate_limiter = MemoryRateLimiter()

    @property
    def name(self) -> str:
        return "sqlite"

    @property
    def lock(self) -> DistributedLock:
        return self._lock

    @property
    def rate_limiter(self) -> RateLimiter:
        return self._rate_limiter

    async def startup(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass
