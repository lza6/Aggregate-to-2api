"""Redis 分布式存储适配器（集群模式，支持高并发分布式锁与滑动窗口 Lua 限流）。"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from .base import DistributedLock, RateLimiter, StorageAdapter

log = logging.getLogger("storage.redis")

# 滑动窗口限流 Lua 脚本（原子性）：清理窗口外记录，添加当前时间戳，判断总量
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

-- 清除过期记录
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)

-- 获取当前计数
local current = redis.call('ZCARD', key)
if current < limit then
    redis.call('ZADD', key, now, now .. '-' .. math.random(100000, 999999))
    redis.call('PEXPIRE', key, math.ceil(window * 1000))
    return 1
else
    return 0
end
"""

# 分布式安全释放锁 Lua 脚本（确保仅释放自己持有的 token）
_RELEASE_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class RedisLock(DistributedLock):
    """基于 Redis SET NX EX 的标准分布式互斥锁。"""

    def __init__(self, client) -> None:
        self._client = client

    async def acquire(self, key: str, holder: str, ttl: float = 60.0, timeout: float | None = None) -> str | None:
        redis_key = f"if:lock:{key}"
        token = f"{holder}:{uuid.uuid4().hex}"
        deadline = time.monotonic() + timeout if timeout is not None else None
        px = int(ttl * 1000)

        while True:
            if deadline is not None and time.monotonic() > deadline:
                return None
            try:
                # SET key token NX PX px
                ok = await self._client.set(redis_key, token, nx=True, px=px)
                if ok:
                    return token
            except Exception as e:
                log.warning("RedisLock acquire 异常: %s", e)
            await asyncio.sleep(0.3)

    async def release(self, key: str, token: str | None) -> bool:
        if not token:
            return False
        redis_key = f"if:lock:{key}"
        try:
            res = await self._client.eval(_RELEASE_LOCK_LUA, 1, redis_key, token)
            return bool(res)
        except Exception as e:
            log.warning("RedisLock release 异常: %s", e)
            return False


class RedisRateLimiter(RateLimiter):
    """基于 Redis ZSET + Lua 脚本的高性能分布式滑动窗口限流器。"""

    def __init__(self, client) -> None:
        self._client = client

    async def is_allowed(self, key: str, limit: int, window: float = 60.0) -> bool:
        if limit <= 0:
            return True
        redis_key = f"if:ratelimit:{key}"
        now = time.time()
        try:
            res = await self._client.eval(_SLIDING_WINDOW_LUA, 1, redis_key, now, window, limit)
            return int(res) == 1
        except Exception as e:
            log.error("RedisRateLimiter Lua 失败，降级放行: %s", e)
            return True

    async def get_count(self, key: str, window: float = 60.0) -> int:
        redis_key = f"if:ratelimit:{key}"
        now = time.time()
        try:
            await self._client.zremrangebyscore(redis_key, "-inf", now - window)
            return await self._client.zcard(redis_key)
        except Exception as e:
            log.warning("RedisRateLimiter get_count 异常: %s", e)
            return 0

    async def reset(self, key: str) -> None:
        redis_key = f"if:ratelimit:{key}"
        try:
            await self._client.delete(redis_key)
        except Exception as e:
            log.warning("RedisRateLimiter reset 异常: %s", e)


class RedisStorageAdapter(StorageAdapter):
    """Redis 分布式存储驱动。"""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client = None
        self._lock = None
        self._rate_limiter = None

    @property
    def name(self) -> str:
        return "redis"

    @property
    def lock(self) -> DistributedLock:
        if self._lock is None:
            raise RuntimeError("RedisStorageAdapter 尚未初始化，请先调用 startup()")
        return self._lock

    @property
    def rate_limiter(self) -> RateLimiter:
        if self._rate_limiter is None:
            raise RuntimeError("RedisStorageAdapter 尚未初始化，请先调用 startup()")
        return self._rate_limiter

    async def startup(self) -> None:
        try:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
            # 测试 ping
            await self._client.ping()
            self._lock = RedisLock(self._client)
            self._rate_limiter = RedisRateLimiter(self._client)
            log.info("Redis 存储驱动已成功连接: %s", self._redis_url)
        except Exception as e:
            log.error("Redis 存储驱动初始化失败: %s", e)
            raise

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            self._lock = None
            self._rate_limiter = None
