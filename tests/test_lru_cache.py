"""LRUCache 单元测试：TTL 命中、过期、maxsize 淘汰、clear、并发安全。"""

import asyncio

import pytest

from api.cache import LRUCache


@pytest.mark.asyncio
async def test_get_set_within_ttl():
    """TTL 内 get 应返回缓存值。"""
    cache = LRUCache(maxsize=128, ttl=5)
    await cache.set("key1", "hello")
    assert await cache.get("key1") == "hello"


@pytest.mark.asyncio
async def test_cache_hits_repeatedly():
    """同一 key 在 TTL 内多次 get 均应命中。"""
    cache = LRUCache(maxsize=128, ttl=5)
    await cache.set("key", 42)
    for _ in range(5):
        assert await cache.get("key") == 42


@pytest.mark.asyncio
async def test_ttl_expiry():
    """TTL 过期后 get 应返回 None。"""
    cache = LRUCache(maxsize=128, ttl=0.1)
    await cache.set("key", "value")
    assert await cache.get("key") == "value"
    await asyncio.sleep(0.2)
    assert await cache.get("key") is None


@pytest.mark.asyncio
async def test_maxsize_eviction():
    """超出 maxsize 时淘汰最久未用的条目。"""
    cache = LRUCache(maxsize=2, ttl=60)
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.set("c", 3)  # 应淘汰 "a"
    assert await cache.get("a") is None
    assert await cache.get("b") == 2
    assert await cache.get("c") == 3


@pytest.mark.asyncio
async def test_maxsize_lru_ordering():
    """LRU 顺序：访问过的条目应被保留，未访问的被淘汰。"""
    cache = LRUCache(maxsize=2, ttl=60)
    await cache.set("a", 1)
    await cache.set("b", 2)
    # 访问 "a"，使其成为最近使用
    assert await cache.get("a") == 1
    await cache.set("c", 3)  # 应淘汰 "b"（最久未用）
    assert await cache.get("a") == 1
    assert await cache.get("b") is None
    assert await cache.get("c") == 3


@pytest.mark.asyncio
async def test_clear():
    """clear() 应清空所有条目。"""
    cache = LRUCache(maxsize=128, ttl=60)
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.clear()
    assert await cache.get("a") is None
    assert await cache.get("b") is None


@pytest.mark.asyncio
async def test_invalidate_specific_key():
    """invalidate(key) 应只删除指定 key。"""
    cache = LRUCache(maxsize=128, ttl=60)
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.invalidate("a")
    assert await cache.get("a") is None
    assert await cache.get("b") == 2


@pytest.mark.asyncio
async def test_set_overwrites_existing():
    """set 同一 key 应覆盖旧值并刷新 TTL。"""
    cache = LRUCache(maxsize=128, ttl=60)
    await cache.set("key", "old")
    await cache.set("key", "new")
    assert await cache.get("key") == "new"


@pytest.mark.asyncio
async def test_set_per_key_ttl_overrides_global():
    """P1-3: 显式 ttl 覆盖全局 TTL（热数据短/冷数据长分层）。"""
    cache = LRUCache(maxsize=128, ttl=60)  # 全局 60s
    await cache.set("hot", "v", ttl=0.05)  # 热数据 0.05s
    assert await cache.get("hot") == "v"
    await asyncio.sleep(0.1)
    assert await cache.get("hot") is None  # 按短 TTL 过期


@pytest.mark.asyncio
async def test_set_ttl_none_uses_global():
    """ttl=None 走全局 TTL（向后兼容旧调用）。"""
    cache = LRUCache(maxsize=128, ttl=60)
    await cache.set("k", "v", ttl=None)
    assert await cache.get("k") == "v"  # 60s 内不过期


@pytest.mark.asyncio
async def test_set_ttl_zero_immediate_expiry():
    """ttl=0 → 立即过期（边界）。"""
    cache = LRUCache(maxsize=128, ttl=60)
    await cache.set("k", "v", ttl=0)
    await asyncio.sleep(0.05)  # v7.7.13: 加大 sleep 防 monotonic 精度不足 + 组合串扰
    assert await cache.get("k") is None  # deadline=now+0，已流逝 → 过期


@pytest.mark.asyncio
async def test_set_ttl_negative_clamped_to_zero():
    """负 ttl 被 max(0,.) 钳制，不抛异常。"""
    cache = LRUCache(maxsize=128, ttl=60)
    await cache.set("k", "v", ttl=-5)  # 不抛
    await asyncio.sleep(0.01)
    assert await cache.get("k") is None  # 钳到 0 → 立即过期


@pytest.mark.asyncio
async def test_set_mixed_ttl_independent_expiry():
    """同池不同 TTL 的 key 独立过期（冷热分层不互相拖累）。"""
    cache = LRUCache(maxsize=128, ttl=60)
    await cache.set("cold", "long", ttl=10)
    await cache.set("hot", "short", ttl=0.05)
    await asyncio.sleep(0.1)
    assert await cache.get("hot") is None
    assert await cache.get("cold") == "long"


@pytest.mark.asyncio
async def test_reaper_cleans_expired():
    """后台 reaper 协程应定期清理过期条目。"""
    cache = LRUCache(maxsize=128, ttl=0.1)
    cache.start_reaper()
    try:
        await cache.set("a", 1)
        await asyncio.sleep(0.3)
        assert await cache.get("a") is None
    finally:
        await cache.stop_reaper()


@pytest.mark.asyncio
async def test_stop_reaper_clears():
    """stop_reaper 应停止后台协程并清空缓存。"""
    cache = LRUCache(maxsize=128, ttl=60)
    cache.start_reaper()
    await cache.set("a", 1)
    await cache.stop_reaper()
    assert cache._reaper_task is None
    assert await cache.get("a") is None


@pytest.mark.asyncio
async def test_concurrent_safety():
    """并发读写不应导致异常或数据损坏。"""
    cache = LRUCache(maxsize=100, ttl=60)

    async def worker(key: str) -> None:
        for _ in range(50):
            await cache.set(key, key)
            v = await cache.get(key)
            assert v in (key, None)

    await asyncio.gather(*[worker(f"k{i}") for i in range(10)])


@pytest.mark.asyncio
async def test_concurrent_get_set_mixed():
    """混合并发：部分协程只读，部分读写，不应死锁。"""
    cache = LRUCache(maxsize=50, ttl=60)
    for i in range(20):
        await cache.set(f"k{i}", i)

    async def writer() -> None:
        for i in range(20, 40):
            await cache.set(f"k{i}", i)
            _ = await cache.get(f"k{i-10}")

    async def reader() -> None:
        for _ in range(50):
            for i in range(20):
                await cache.get(f"k{i}")

    await asyncio.gather(writer(), writer(), reader(), reader())


@pytest.mark.asyncio
async def test_missing_key_returns_none():
    """不存在的 key 应返回 None。"""
    cache = LRUCache(maxsize=128, ttl=5)
    assert await cache.get("nonexistent") is None


@pytest.mark.asyncio
async def test_snapshot():
    """snapshot() 返回当前缓存状态。"""
    cache = LRUCache(maxsize=128, ttl=5)
    snap = await cache.snapshot()
    assert snap["size"] == 0
    assert snap["maxsize"] == 128
    assert snap["ttl"] == 5

    await cache.set("a", 1)
    snap = await cache.get("a")  # 先确认 set 成功
    snap = await cache.snapshot()
    assert snap["size"] == 1


@pytest.mark.asyncio
async def test_cache_hits_miss_db_mock():
    """模拟 DB 读取计数器验证缓存命中减少 DB 调用。"""
    call_count = 0

    async def fake_db_query() -> str:
        nonlocal call_count
        call_count += 1
        return "db_result"

    cache = LRUCache(maxsize=128, ttl=5)

    # 第一次：未命中，回源查询
    result = await cache.get("test_key")
    assert result is None

    val = await fake_db_query()
    await cache.set("test_key", val)
    assert call_count == 1

    # 第二次：命中缓存，不调 DB
    result = await cache.get("test_key")
    assert result == "db_result"
    assert call_count == 1  # DB 未增加

    # 第三次：仍然命中
    result = await cache.get("test_key")
    assert result == "db_result"
    assert call_count == 1


@pytest.mark.asyncio
async def test_ttl_expiry_db_reread():
    """TTL 过期后应重新查询 DB（通过计数器模拟验证）。"""
    call_count = 0

    async def fake_db_query() -> str:
        nonlocal call_count
        call_count += 1
        return f"result_{call_count}"

    cache = LRUCache(maxsize=128, ttl=0.1)
    val = await fake_db_query()
    await cache.set("key", val)
    assert call_count == 1

    # 等待过期
    await asyncio.sleep(0.2)

    # 缓存失效，应再次查询 DB
    cached = await cache.get("key")
    assert cached is None  # 已过期

    val2 = await fake_db_query()
    await cache.set("key", val2)
    assert call_count == 2
