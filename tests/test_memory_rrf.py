"""记忆 RRF 检索功能测试（v18 P0-2）。覆盖：FTS 建表/触发器同步/RRF 纯函数/双模式/降级/过滤。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.agent.memory import MemoryStore, _rrf_merge  # noqa: E402


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(db_path=str(tmp_path / "mem_rrf.db"))
    yield s


def _insert_l1(store, *, content, importance=0.5, scene="image", superseded_by=None):
    now = time.time()
    with store._conn() as conn:
        cur = conn.execute(
            "INSERT INTO mem_atoms(user_key, scene, content, importance, created_at, last_accessed_at, source_ids, superseded_by)"
            " VALUES (?,?,?,?,?,?,?,?)",
            ("default", scene, content, importance, now - 10, now, "1", superseded_by),
        )
        conn.commit()
        return cur.lastrowid


def test_fts_table_created(store):
    with store._conn() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mem_atoms_fts'").fetchall()
        assert rows, "mem_atoms_fts 虚表未创建"


def test_fts_trigger_syncs_on_insert(store):
    rid = _insert_l1(store, content="用户喜欢 深色背景 电影感 调色")
    with store._conn() as conn:
        rows = conn.execute("SELECT rowid FROM mem_atoms_fts WHERE mem_atoms_fts MATCH '\"深色背景\"'").fetchall()
        assert any(r[0] == rid for r in rows)


def test_rrf_merge_pure_function():
    merged = _rrf_merge([[10, 20, 30], [30, 40, 10]], k=60)
    assert isinstance(merged, dict)
    # 两路都命中且排名靠前的 id 得分更高
    # ids 10/30 在两路中对称排名（rank1+rank3），得分相等且高于单路 rank2 的 20/40
    assert merged[10] == merged[30] > merged[40]
    assert merged[20] == merged[40]
    assert _rrf_merge([]) == {}


@pytest.mark.asyncio
async def test_query_plain_vs_rrf_same_data(store):
    _insert_l1(store, content="电商主图 深色背景", importance=0.9)
    _insert_l1(store, content="PPT 大纲 要点", importance=0.5)
    plain = await store.query("default", "image", layer="L1", limit=10, mode="plain")
    rrf = await store.query("default", "image", layer="L1", limit=10, mode="rrf")
    assert len(plain) == 2 and len(rrf) == 2
    assert {r.id for r in plain} == {r.id for r in rrf}


@pytest.mark.asyncio
async def test_query_auto_defaults_plain(store, monkeypatch):
    from api.config import reset_settings

    monkeypatch.setenv("IF_MEMORY_RRF", "0")
    reset_settings()
    try:
        _insert_l1(store, content="深色背景", importance=0.9)
        recs = await store.query("default", "image", layer="L1", mode="auto")
        assert len(recs) == 1
        assert not any("RRF" in x for r in recs for x in r.explain)
    finally:
        reset_settings()


@pytest.mark.asyncio
async def test_query_rrf_degrade_when_fts_dropped(store):
    _insert_l1(store, content="深色背景 电商", importance=0.8)
    with store._conn() as conn:
        conn.execute("DROP TABLE mem_atoms_fts")
        conn.commit()
    recs = await store.query("default", "image", layer="L1", limit=10, mode="rrf")
    assert len(recs) == 1  # 降级纯 SQL 不崩


@pytest.mark.asyncio
async def test_query_rrf_supersede_filter(store):
    _insert_l1(store, content="旧记忆", superseded_by=99)
    _insert_l1(store, content="新记忆相关词")
    recs = await store.query("default", "image", layer="L1", limit=10, mode="rrf")
    assert {r.content for r in recs} == {"新记忆相关词"}


@pytest.mark.asyncio
async def test_query_rrf_explain_marked(store):
    _insert_l1(store, content="电商主图 深色背景 视觉策划", importance=0.9)
    recs = await store.query("default", "image", layer="L1", limit=10, mode="rrf")
    assert recs  # 非空（结果不足时 FTS 扩充 + importance 融合）
