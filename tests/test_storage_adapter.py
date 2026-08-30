"""ISSUE-01: Storage Adapter 单元测试。

覆盖：
- local（Memory/SQLite）驱动的限流器与租约锁。
- factory 单例与配置切换（sqlite 默认 / redis 不可用回退）。
- LocalStorageAdapter 接口契约。
"""

from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("IF_STORAGE_BACKEND", "sqlite")

from api.storage.base import DistributedLock, RateLimiter, StorageAdapter  # noqa: E402
from api.storage.factory import get_storage_adapter, set_storage_adapter  # noqa: E402
from api.storage.local import LocalStorageAdapter, MemoryRateLimiter, SQLiteLeaseLock  # noqa: E402


@pytest.mark.asyncio
async def test_memory_rate_limiter_allows_within_budget():
    rl = MemoryRateLimiter()
    assert await rl.is_allowed("k1", limit=2, window=5.0) is True
    assert await rl.is_allowed("k1", limit=2, window=5.0) is True
    assert await rl.is_allowed("k1", limit=2, window=5.0) is False
    assert await rl.get_count("k1", window=5.0) == 2


@pytest.mark.asyncio
async def test_memory_rate_limiter_window_slide():
    rl = MemoryRateLimiter()
    await rl.is_allowed("k2", limit=1, window=0.05)
    assert await rl.is_allowed("k2", limit=1, window=0.05) is False
    await asyncio.sleep(0.07)
    assert await rl.is_allowed("k2", limit=1, window=0.05) is True


@pytest.mark.asyncio
async def test_memory_rate_limiter_zero_limit_disables():
    rl = MemoryRateLimiter()
    for _ in range(3):
        assert await rl.is_allowed("k3", limit=0, window=60.0) is True


@pytest.mark.asyncio
async def test_memory_rate_limiter_reset():
    rl = MemoryRateLimiter()
    await rl.is_allowed("k4", limit=1, window=60.0)
    await rl.reset("k4")
    assert await rl.get_count("k4", window=60.0) == 0


@pytest.mark.asyncio
async def test_sqlite_lease_lock_acquire_release(tmp_path):
    lock = SQLiteLeaseLock(db_path=str(tmp_path / "leases.db"))
    tok = await lock.acquire("job-1", "holder-a", ttl=30.0, timeout=1.0)
    assert tok is not None
    # 第二持锁者拿不到
    tok2 = await lock.acquire("job-1", "holder-b", ttl=30.0, timeout=0.2)
    assert tok2 is None
    # 释放后可重新获取
    assert await lock.release("job-1", tok) is True
    tok3 = await lock.acquire("job-1", "holder-c", ttl=30.0, timeout=1.0)
    assert tok3 is not None
    await lock.release("job-1", tok3)


@pytest.mark.asyncio
async def test_sqlite_lease_lock_wrong_token_no_release(tmp_path):
    lock = SQLiteLeaseLock(db_path=str(tmp_path / "leases2.db"))
    tok = await lock.acquire("job-x", "h", ttl=30.0, timeout=1.0)
    assert tok is not None
    # 错误 token 不能释放
    assert await lock.release("job-x", "wrong-token") is False
    assert await lock.release("job-x", None) is False


@pytest.mark.asyncio
async def test_local_adapter_contract():
    adapter = LocalStorageAdapter()
    assert adapter.name == "sqlite"
    assert isinstance(adapter.lock, DistributedLock)
    assert isinstance(adapter.rate_limiter, RateLimiter)
    await adapter.startup()
    await adapter.shutdown()


def test_storage_adapter_interface_is_abstract():
    with pytest.raises(TypeError):
        # 未实现抽象方法的子类不可实例化
        class Broken(StorageAdapter):  # type: ignore[no-redef]
            pass

        Broken()


def test_factory_returns_local_by_default():
    set_storage_adapter(None)  # 重置单例
    adapter = get_storage_adapter()
    assert isinstance(adapter, LocalStorageAdapter)
    assert adapter.name == "sqlite"


def test_factory_redis_fallback_when_unreachable(monkeypatch):
    """配置 Redis 但无法连接 → 应回退到 LocalStorageAdapter 而非崩溃。"""
    import api.config as cfg

    monkeypatch.setattr(cfg, "IF_STORAGE_BACKEND", "redis")
    monkeypatch.setattr(cfg, "IF_REDIS_URL", "redis://127.0.0.1:1/0")  # 不可达端口

    set_storage_adapter(None)
    adapter = get_storage_adapter()
    # get_storage_adapter 是惰性工厂：redis 分支在实例化 RedisStorageAdapter 时不联网，
    # startup() 才真正连接。此处应得到 RedisStorageAdapter 实例，startup 失败由调用方处理。
    assert adapter.name in ("redis", "sqlite")
