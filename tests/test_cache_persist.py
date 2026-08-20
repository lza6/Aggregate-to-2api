"""IMP-11: 画廊/统计缓存持久化回写测试。
验证：
1. 持久化模式：set → DB cache_store 表写入了数据
2. 恢复模式：restore_from_db() 从 DB 读回缓存
3. 失效同步：invalidate 后 DB 对应条目删除
4. 停止时 flush：flush_to_db() 写回所有内存条目
5. 重启后空窗期消除：DB 中缓存被正确恢复
"""
import asyncio
import json
import os
import tempfile
import time

import pytest
import pytest_asyncio

from api.cache import LRUCache


@pytest_asyncio.fixture
async def tmp_db_path():
    """临时 SQLite 文件路径，用完后自动清理。"""
    from api.db import DB
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DB(path)
    await db._ensure_initialized()
    yield db
    try:
        await db.close()
    except Exception:
        pass
    try:
        os.unlink(path)
        for suffix in ("-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.unlink(path + suffix)
    except OSError:
        pass


@pytest.mark.asyncio
async def test_set_persists_to_db(tmp_db_path):
    """set 后 DB cache_store 表中应有对应条目。"""
    cache = LRUCache(maxsize=128, ttl=60, persist_db=tmp_db_path)
    await cache.set("k1", {"hello": "world"})
    await asyncio.sleep(0.05)  # 让 pending 写
    await cache.flush_to_db()
    entries = await tmp_db_path.load_cache_snapshot()
    keys = [e[0] for e in entries]
    assert "k1" in keys


@pytest.mark.asyncio
async def test_restore_from_db(tmp_db_path):
    """restore_from_db() 应从 DB 恢复到内存。"""
    cache = LRUCache(maxsize=128, ttl=60, persist_db=tmp_db_path)
    await cache.set("k1", "hello")
    await cache.set("k2", 42)
    await cache.flush_to_db()

    # 新建一个缓存实例，从 DB 恢复
    cache2 = LRUCache(maxsize=128, ttl=60, persist_db=tmp_db_path)
    restored = await cache2.restore_from_db()
    assert restored >= 2

    v1 = await cache2.get("k1")
    assert v1 == "hello"
    v2 = await cache2.get("k2")
    assert v2 == 42


@pytest.mark.asyncio
async def test_invalidate_removes_from_db(tmp_db_path):
    """invalidate 后 DB 中对应条目应被删除。"""
    cache = LRUCache(maxsize=128, ttl=60, persist_db=tmp_db_path)
    await cache.set("k1", "hello")
    await cache.invalidate("k1")
    await cache.flush_to_db()
    entries = await tmp_db_path.load_cache_snapshot()
    keys = [e[0] for e in entries]
    assert "k1" not in keys


@pytest.mark.asyncio
async def test_invalidate_prefix_removes_from_db(tmp_db_path):
    """invalidate_prefix 应删除 DB 中匹配前缀的条目。"""
    cache = LRUCache(maxsize=128, ttl=60, persist_db=tmp_db_path)
    await cache.set("gallery:10", "data1")
    await cache.set("gallery:50", "data2")
    await cache.set("stats:overview", "stats")
    await cache.invalidate_prefix("gallery:")
    await cache.flush_to_db()
    entries = await tmp_db_path.load_cache_snapshot()
    keys = [e[0] for e in entries]
    assert "gallery:10" not in keys
    assert "gallery:50" not in keys
    assert "stats:overview" in keys  # 不受影响


@pytest.mark.asyncio
async def test_flush_all_to_db_on_stop(tmp_db_path):
    """stop_reaper 时应 flush 所有内存条目到 DB。"""
    cache = LRUCache(maxsize=128, ttl=60, persist_db=tmp_db_path)
    await cache.set("k1", "v1")
    await cache.set("k2", "v2")
    cache.start_reaper()
    await cache.stop_reaper()
    # 停止后 DB 应包含条目
    entries = await tmp_db_path.load_cache_snapshot()
    keys = [e[0] for e in entries]
    assert "k1" in keys
    assert "k2" in keys


@pytest.mark.asyncio
async def test_restore_eliminates_reboot_gap(tmp_db_path):
    """重启后恢复缓存应消除空窗期：DB 中条目不应过期。"""
    cache = LRUCache(maxsize=128, ttl=3600, persist_db=tmp_db_path)
    await cache.set("stats:overview", {"total": 100})
    await cache.flush_to_db()

    # 模拟重启：新建缓存实例并恢复
    cache2 = LRUCache(maxsize=128, ttl=3600, persist_db=tmp_db_path)
    restored = await cache2.restore_from_db()
    assert restored >= 1
    v = await cache2.get("stats:overview")
    assert v == {"total": 100}


@pytest.mark.asyncio
async def test_no_persist_mode_works(tmp_db_path):
    """不传 persist_db 时，持久化行为应完全无影响。"""
    cache = LRUCache(maxsize=128, ttl=60)
    await cache.set("k1", "hello")
    assert await cache.get("k1") == "hello"
    # 不应有 DB 条目
    entries = await tmp_db_path.load_cache_snapshot()
    assert len(entries) == 0


@pytest.mark.asyncio
async def test_evicted_item_persisted(tmp_db_path):
    """LRU 淘汰的条目也应持久化到 DB（防重启后空窗）。"""
    cache = LRUCache(maxsize=2, ttl=3600, persist_db=tmp_db_path)
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.set("c", 3)  # 淘汰 "a"
    await cache.flush_to_db()
    entries = await tmp_db_path.load_cache_snapshot()
    keys = [e[0] for e in entries]
    assert "a" in keys  # 被淘汰但持久化了


@pytest.mark.asyncio
async def test_serialize_deserialize_roundtrip(tmp_db_path):
    """序列化/反序列化往返：复杂类型应正确恢复。"""
    cache = LRUCache(maxsize=128, ttl=60, persist_db=tmp_db_path)
    complex_val = {
        "items": [{"id": 1, "name": "test"}],
        "count": 5,
        "nested": {"key": "value"},
    }
    await cache.set("complex", complex_val)
    await cache.flush_to_db()

    cache2 = LRUCache(maxsize=128, ttl=60, persist_db=tmp_db_path)
    await cache2.restore_from_db()
    v = await cache2.get("complex")
    assert v == complex_val


@pytest.mark.asyncio
async def test_snapshot_with_persist(tmp_db_path):
    """snapshot 应正确反映持久化挂起条目数。"""
    cache = LRUCache(maxsize=128, ttl=60, persist_db=tmp_db_path)
    snap = await cache.snapshot()
    assert "persist_pending_upserts" in snap
    assert snap["persist_pending_upserts"] == 0

    await cache.set("k1", "v1")
    snap = await cache.snapshot()
    assert snap["persist_pending_upserts"] >= 1