"""Redis 存储适配器单元测试（P0-3：孤儿模块兜底覆盖，无真实 Redis 依赖）。

覆盖：
- RedisLock / RedisRateLimiter 的初始化前置校验（未 startup 即访问 → RuntimeError）。
- 滑动窗口 Lua 脚本与释放锁 Lua 脚本的语法正确性（用 fake client 走 eval 路径）。
- fake client 故障时限流器 fail-open（放行）、锁 acquire 重试、release 异常吞掉。
- startup 成功路径（fake redis.asyncio 注入 sys.modules，免装依赖）。
- shutdown 清理。

设计：redis 包未安装（可选依赖，IF_REDIS_ENABLED 默认 False），
全部通过 FakeRedis 模拟 redis.asyncio 的 awaitable 接口（ZSET 语义简化），
只验证 RedisStorageAdapter 自身逻辑，不验证真实 Redis 行为。
"""

from __future__ import annotations

import asyncio
import sys
import time
import types

import pytest

from api.storage.base import DistributedLock, RateLimiter


def _run_restoring(coro):
    """asyncio.run 会 set_event_loop 到新 loop 且不恢复——包一层保存/恢复，
    避免后续 pytest-asyncio 测试 create_task 挂到已关闭 loop（token_pool 批量失败根因）。

    v10.0.0 flaky 修复：conftest 的 _reset_event_loop_after 在每用例后把 policy
    当前 loop 置为 None（set_event_loop(None)），当 sync 测试在全量中继前序用例
    之后运行、且当前无 loop 时，policy.get_event_loop() 在 Python 3.11 直接抛
    RuntimeError("There is no current event loop")（如 test_startup_success_
    injects_lock_and_limiter 在组合/全量下失败）。这里把「取 old loop」改为容错：
    无 loop 视为 None，asyncio.run 后无需恢复（它自身会 set 新 loop 并在 finally
    close + set_event_loop(None)），仅当确有未关闭的 old loop 才恢复。
    由此组合/全量下不再因取 loop 抛错而中断，也消除对后续 async 测试的污染。
    """
    import asyncio

    policy = asyncio.get_event_loop_policy()
    try:
        old = policy.get_event_loop()
    except RuntimeError:
        old = None
    try:
        return asyncio.run(coro)
    finally:
        if old is not None and not old.is_closed():
            policy.set_event_loop(old)

from api.storage.redis_adapter import RedisLock, RedisRateLimiter, RedisStorageAdapter

# ── Fake redis.asyncio 客户端 ───────────────────────────────


class FakeRedis:
    """模拟 redis.asyncio.Redis 的最小接口（set/eval/zcard/delete/ping/aclose）。

    行为可注入：fail=True 时所有命令抛 ConnectionError（测降级路径）。
    eval 按脚本内容分派：滑窗脚本走内存 ZSET 简化语义；释放锁脚本走 token 比对。
    """

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.store: dict[str, str] = {}  # string 锁
        self.zsets: dict[str, list[tuple[float, str]]] = {}  # 滑窗
        self.calls: list[str] = []

    async def _maybe_fail(self, name: str) -> None:
        self.calls.append(name)
        if self.fail:
            raise ConnectionError("redis down")

    async def set(self, key, value, nx=False, px=None):
        await self._maybe_fail("set")
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def get(self, key):
        await self._maybe_fail("get")
        return self.store.get(key)

    async def eval(self, script, numkeys, *keys_and_args):
        await self._maybe_fail("eval")
        if "ZREMRANGEBYSCORE" in script:
            # 滑窗 Lua：key/now/window/limit
            key, now, window, limit = keys_and_args
            z = self.zsets.setdefault(key, [])
            z[:] = [(s, m) for s, m in z if now - s < window]
            if len(z) < limit:
                member = f"{now}-fake"
                z.append((now, member))
                return 1
            return 0
        if 'redis.call("get"' in script:
            # 释放锁 Lua：token 比对
            key, token = keys_and_args
            if self.store.get(key) == token:
                del self.store[key]
                return 1
            return 0
        raise ValueError(f"未识别脚本: {script[:40]}")

    async def zremrangebyscore(self, key, lo, hi):
        await self._maybe_fail("zremrangebyscore")
        lo, hi = float(lo), float(hi)
        z = self.zsets.get(key, [])
        return sum(1 for s, _ in z if not (lo <= s <= hi))

    async def zcard(self, key):
        await self._maybe_fail("zcard")
        return len(self.zsets.get(key, []))

    async def delete(self, key):
        await self._maybe_fail("delete")
        self.store.pop(key, None)
        self.zsets.pop(key, None)
        return 1

    async def ping(self):
        await self._maybe_fail("ping")
        return True

    async def aclose(self):
        await self._maybe_fail("aclose")


# ── 前置校验：未 startup 就用 → RuntimeError ────────────────


def test_lock_and_limiter_require_startup():
    adapter = RedisStorageAdapter("redis://127.0.0.1:6379/0")
    with pytest.raises(RuntimeError):
        _ = adapter.lock
    with pytest.raises(RuntimeError):
        _ = adapter.rate_limiter
    assert adapter.name == "redis"


# ── startup 成功路径（fake redis.asyncio 模块注入）────────────


def test_startup_success_injects_lock_and_limiter(monkeypatch):
    fake_mod = types.ModuleType("redis")
    fake_asyncio = types.ModuleType("redis.asyncio")
    fake_asyncio.from_url = lambda *a, **kw: FakeRedis()
    fake_mod.asyncio = fake_asyncio
    monkeypatch.setitem(sys.modules, "redis", fake_mod)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_asyncio)

    adapter = RedisStorageAdapter("redis://fake:6379/0")
    asyncio.get_event_loop_policy()
    _run_restoring(adapter.startup())
    try:
        assert isinstance(adapter.lock, DistributedLock)
        assert isinstance(adapter.rate_limiter, RateLimiter)
        assert adapter.name == "redis"
    finally:
        _run_restoring(adapter.shutdown())
    assert adapter._client is None  # shutdown 清理


def test_startup_failure_raises(monkeypatch):
    fake_mod = types.ModuleType("redis")
    fake_asyncio = types.ModuleType("redis.asyncio")
    fake_asyncio.from_url = lambda *a, **kw: FakeRedis(fail=True)
    fake_mod.asyncio = fake_asyncio
    monkeypatch.setitem(sys.modules, "redis", fake_mod)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_asyncio)

    adapter = RedisStorageAdapter("redis://fake:6379/0")
    with pytest.raises(Exception):
        _run_restoring(adapter.startup())


# ── RedisLock：acquire/release + 故障重试 ───────────────────


@pytest.mark.asyncio
async def test_redis_lock_acquire_release_roundtrip():
    client = FakeRedis()
    lock = RedisLock(client)
    token = await lock.acquire("k", "holder", ttl=5.0)
    assert token is not None and token.startswith("holder:")
    # 他人 token 无法释放
    assert await lock.release("k", "wrong") is False
    # 正确 token 释放成功
    assert await lock.release("k", token) is True
    # None token 直接 False
    assert await lock.release("k", None) is False


@pytest.mark.asyncio
async def test_redis_lock_acquire_nx_conflict():
    client = FakeRedis()
    lock = RedisLock(client)
    t1 = await lock.acquire("k2", "h1", ttl=5.0)
    assert t1 is not None
    # 已被持有（NX 冲突）→ 轮询直到 timeout
    t2 = await lock.acquire("k2", "h2", ttl=5.0, timeout=0.4)
    assert t2 is None


@pytest.mark.asyncio
async def test_redis_lock_release_on_fail_returns_false():
    client = FakeRedis(fail=True)
    lock = RedisLock(client)
    assert await lock.release("k", "tok") is False
    assert await lock.acquire("k", "h", ttl=1.0, timeout=0.2) is None  # 一直故障 → timeout None


# ── RedisRateLimiter：滑窗 + 故障 fail-open ─────────────────


@pytest.mark.asyncio
async def test_redis_rate_limiter_window():
    client = FakeRedis()
    rl = RedisRateLimiter(client)
    assert await rl.is_allowed("rk", limit=2, window=5.0) is True
    assert await rl.is_allowed("rk", limit=2, window=5.0) is True
    assert await rl.is_allowed("rk", limit=2, window=5.0) is False
    assert await rl.get_count("rk", window=5.0) == 2
    await rl.reset("rk")
    assert await rl.get_count("rk", window=5.0) == 0


@pytest.mark.asyncio
async def test_redis_rate_limiter_zero_limit_open():
    rl = RedisRateLimiter(FakeRedis())
    assert await rl.is_allowed("rk2", limit=0, window=60.0) is True


@pytest.mark.asyncio
async def test_redis_rate_limiter_fail_open():
    """Redis 故障 → fail-open 放行（日志告警，不阻塞业务）。"""
    rl = RedisRateLimiter(FakeRedis(fail=True))
    assert await rl.is_allowed("rk3", limit=1, window=5.0) is True
    assert await rl.get_count("rk3", window=5.0) == 0
    await rl.reset("rk3")  # 异常吞掉不抛


@pytest.mark.asyncio
async def test_redis_rate_limiter_real_window_semantics():
    """验证 Lua 简化语义：窗口滑动后可重新通过（与 local MemoryRateLimiter 行为对齐）。"""
    client = FakeRedis()
    rl = RedisRateLimiter(client)
    now = time.time()
    # 直接预置过期记录
    client.zsets["if:ratelimit:rk4"] = [(now - 10.0, "old")]
    assert await rl.is_allowed("rk4", limit=1, window=5.0) is True  # 旧记录被清，放行
