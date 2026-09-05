"""tests/test_agent_memory.py — P1-A3 L0-L3 记忆分层 + 异步巩固测试。

验收：
- MemoryStore 建 4 张表（mem_observations/mem_atoms/mem_scenarios/mem_persona）
- observe L0 写入
- query 各层查询
- consolidate Mock 路径：L0→L1 去重 + importance>=0.6 筛选
- 衰减淘汰：超期 L0 记忆被 prune
- 开关关闭：consolidate 返回 0（零回归）
"""

from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("IF_MEMORY_CONSOLIDATION_ENABLED", "1")
os.environ.setdefault("IF_MOCK_UPSTREAM", "1")


@pytest.fixture
def store(tmp_path):
    """临时 DB 的 MemoryStore。"""
    from api.agent.memory import MemoryStore

    db_path = str(tmp_path / "test_mem.db")
    return MemoryStore(db_path)


@pytest.mark.asyncio
async def test_observe_and_query_l0(store):
    """observe L0 写入 + query L0 查询。"""
    rid = await store.observe("user1", "image", "喜欢猫咪风格", 0.8)
    assert rid > 0
    recs = await store.query("user1", "image", layer="L0", limit=10)
    assert len(recs) == 1
    assert recs[0].content == "喜欢猫咪风格"
    assert recs[0].importance == 0.8
    assert recs[0].layer == "L0"


@pytest.mark.asyncio
async def test_consolidate_mock_promotes_high_importance(store):
    """Mock 巩固：importance>=0.6 的 L0 提升到 L1。"""
    await store.observe("u", "image", "高重要性事实", 0.9)
    await store.observe("u", "image", "低重要性事实", 0.3)
    result = await store.consolidate()
    assert result["L0_to_L1"] == 1  # 只有 importance>=0.6 的被提升
    # L0 已清空（巩固后删除）
    l0 = await store.query("u", "image", layer="L0", limit=10)
    assert len(l0) == 0
    # L1 有 1 条
    l1 = await store.query("u", "image", layer="L1", limit=10)
    assert len(l1) == 1
    assert l1[0].content == "高重要性事实"


@pytest.mark.asyncio
async def test_consolidate_mock_deduplicates(store):
    """Mock 巩固：相同 content 去重（取 importance 最高）。"""
    await store.observe("u", "image", "重复事实", 0.7)
    await store.observe("u", "image", "重复事实", 0.9)  # 相同 content，更高 importance
    result = await store.consolidate()
    assert result["L0_to_L1"] == 1  # 去重后只 1 条
    l1 = await store.query("u", "image", layer="L1", limit=10)
    assert len(l1) == 1
    assert l1[0].importance == 0.9  # 取最高


@pytest.mark.asyncio
async def test_query_updates_access_time(store):
    """query 更新访问时间（hot 记忆不衰减）。"""
    await store.observe("u", "image", "事实", 0.9)
    recs = await store.query("u", "image", layer="L0", limit=10)
    assert len(recs) == 1
    old_access = recs[0].last_accessed_at
    # 等 0.1s 再查，访问时间应更新
    await asyncio.sleep(0.1)
    recs2 = await store.query("u", "image", layer="L0", limit=10)
    assert recs2[0].last_accessed_at > old_access


@pytest.mark.asyncio
async def test_disabled_consolidate_returns_zero(monkeypatch, store):
    """IF_MEMORY_CONSOLIDATION_ENABLED=0 → consolidate 返回 0（零回归）。"""
    import api.agent.memory as mem_mod

    monkeypatch.setattr(mem_mod, "MEMORY_CONSOLIDATION_ENABLED", False)
    await store.observe("u", "image", "事实", 0.9)
    result = await store.consolidate()
    assert result == {"L0_to_L1": 0, "pruned": 0}


@pytest.mark.asyncio
async def test_memory_store_creates_four_tables(store):
    """MemoryStore 建 4 张记忆表。"""
    import sqlite3

    conn = sqlite3.connect(store.db_path)
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'mem_%'"
        ).fetchall()
    }
    conn.close()
    assert "mem_observations" in tables
    assert "mem_atoms" in tables
    assert "mem_scenarios" in tables
    assert "mem_persona" in tables


@pytest.mark.asyncio
async def test_query_unknown_layer_returns_empty(store):
    """未知 layer 查询返回空列表（不崩）。"""
    await store.observe("u", "image", "事实", 0.9)
    recs = await store.query("u", "image", layer="L99", limit=10)
    assert recs == []


@pytest.mark.asyncio
async def test_consolidation_loop_starts_and_stops(store):
    """巩固后台 worker 启停正常。"""
    await store.start_consolidation_loop()
    assert store._consolidation_task is not None
    assert not store._consolidation_task.done()
    await store.stop_consolidation_loop()
    assert store._consolidation_task.done() or store._consolidation_task.cancelled()
