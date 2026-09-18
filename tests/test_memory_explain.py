"""记忆 explain 测试（指南 B4 / P1-1，mem0 explain 对标）。

覆盖：query() 返回 explain 命中理由（importance 档/新鲜度/有效态）、supersede 过滤、
MemoryRecord.explain 字段、_build_explain 纯函数、路由 /v1/agent/memory 透传 explain。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.agent.memory import MemoryRecord, MemoryStore, _build_explain  # noqa: E402


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(db_path=str(tmp_path / "mem_explain.db"))
    yield s


def _insert_l1(store, *, content="用户喜欢深色背景", importance=0.5, accessed_delta=0.0, superseded_by=None, scene="image"):
    """直接向 mem_atoms 插入 L1 行（绕过 consolidate 的 LLM 依赖）。"""
    now = time.time()
    with store._conn() as conn:
        cur = conn.execute(
            "INSERT INTO mem_atoms(user_key, scene, content, importance, created_at, last_accessed_at, source_ids, superseded_by)"
            " VALUES (?,?,?,?,?,?,?,?)",
            ("default", scene, content, importance, now - 10, now - accessed_delta, "1", superseded_by),
        )
        conn.commit()
        return cur.lastrowid


async def test_query_returns_explain_reasons(store):
    _insert_l1(store, importance=0.9, accessed_delta=100)
    recs = await store.query("default", "image", layer="L1")
    assert len(recs) == 1
    rec = recs[0]
    assert isinstance(rec.explain, list) and len(rec.explain) >= 2
    joined = " ".join(rec.explain)
    assert "importance 高" in joined
    assert "近期访问过" in joined


async def test_query_explain_medium_and_old(store):
    _insert_l1(store, importance=0.6, accessed_delta=3 * 86400)
    recs = await store.query("default", "image", layer="L1")
    joined = " ".join(recs[0].explain)
    assert "importance 中等" in joined
    assert "一周内访问过" in joined


async def test_query_filters_superseded_and_explain_valid(store):
    _insert_l1(store, content="旧记忆", superseded_by=99)
    _insert_l1(store, content="新记忆", superseded_by=None)
    recs = await store.query("default", "image", layer="L1")
    assert len(recs) == 1
    assert recs[0].content == "新记忆"
    assert any("未被取代" in x for x in recs[0].explain)


async def test_explain_empty_when_no_records(store):
    assert await store.query("default", "no-scene", layer="L1") == []


def test_build_explain_pure_function():
    r = {"importance": 0.95, "last_accessed_at": time.time(), "superseded_by": None}
    reasons = _build_explain(r, time.time())
    assert any("importance 高" in x for x in reasons)
    assert any("近期访问过" in x for x in reasons)
    assert any("未被取代" in x for x in reasons)


def test_memory_record_explain_field_default():
    rec = MemoryRecord(
        id=1, layer="L1", user_key="default", scene="image", content="x",
        importance=0.5, created_at=0.0, last_accessed_at=0.0, source_ids="",
    )
    assert rec.explain == []


def test_route_memory_returns_explain():
    """路由级透传验证（app 装配慢，仅一个用例）。"""
    import tempfile

    db = str(Path(tempfile.gettempdir()) / "test_mem_explain_routes.db")
    try:
        Path(db).unlink()
    except OSError:
        pass
    os.environ["IF_DB_FILE"] = db
    from api.config import reset_settings

    reset_settings()
    from api.agent.memory import memory_store

    # 注入一条 L1 记忆
    with memory_store._conn() as conn:
        now = time.time()
        conn.execute(
            "INSERT INTO mem_atoms(user_key, scene, content, importance, created_at, last_accessed_at, source_ids)"
            " VALUES (?,?,?,?,?,?,?)",
            ("default", "image", "用户偏好深色背景", 0.9, now - 5, now - 60, "1"),
        )
        conn.commit()
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as c:
        resp = c.get("/v1/agent/memory?scene=image&layer=L1")
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) >= 1
        assert isinstance(items[0]["explain"], list)
        assert len(items[0]["explain"]) >= 1
    os.environ.pop("IF_DB_FILE", None)
    reset_settings()
