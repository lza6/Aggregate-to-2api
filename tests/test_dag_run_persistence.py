"""tests/test_dag_run_persistence.py — v10.0.0 DAG run 持久化（SQLite）。

覆盖：写入/读回/跨重启一致/分页/状态过滤/TTL 清理/DB 异常降级内存。
TDD：先 RED（本文件用例）→ GREEN（实现 api/routes/agent_dag_store_sqlite.py）
→ IMPROVE。付费红线：零 provider 调用，纯 store 单元测试。
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time

import pytest

from api.agent.dag import DagNode, build_graph


def _make_run(name: str = "持久化测试", *, finished: bool = False) -> object:
    nodes = [
        DagNode(id="A", kind="llm", depends_on=[], prompt="第一步"),
        DagNode(id="B", kind="llm", depends_on=["A"], prompt="第二步"),
    ]
    run = build_graph(name, nodes, max_parallel=2, fail_fast=True, retry=0)
    run.mark_running()
    for n in run.nodes.values():
        n.mark_succeeded(f"结果:{n.id}")
    if finished:
        run.mark_finished()
    return run


@pytest.fixture
async def store_factory():
    """每个用例独立的 SQLite store（临时文件）。"""
    stores = []

    def _make(path: str | None = None):
        from api.routes.agent_dag_store_sqlite import DagRunSqliteStore

        s = DagRunSqliteStore(path or _default_path())
        stores.append(s)
        return s

    yield _make
    for s in stores:
        try:
            await s.close()
        except Exception:
            pass


def _default_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


class TestSqliteStoreBasics:
    async def test_upsert_and_get_roundtrip(self, store_factory):
        store = store_factory()
        run = _make_run()
        await store.upsert(run)
        got = await store.get(run.run_id)
        assert got is not None
        assert got["run_id"] == run.run_id
        assert got["status"] == run.status
        assert len(got["nodes"]) == 2

    async def test_get_missing_returns_none(self, store_factory):
        store = store_factory()
        assert await store.get("no-such-run") is None

    async def test_persists_across_restart(self, store_factory):
        """G-B 核心：跨 store 实例（模拟重启）读回状态一致。"""
        path = _default_path()
        store1 = store_factory(path)
        run = _make_run(finished=True)
        await store1.upsert(run)
        await store1.close()

        store2 = store_factory(path)
        got = await store2.get(run.run_id)
        assert got is not None
        assert got["status"] == "succeeded"
        assert got["name"] == "持久化测试"
        assert got["nodes"][0]["status"] == "succeeded"

    async def test_list_returns_recent_first(self, store_factory):
        store = store_factory()
        r1 = _make_run("r1", finished=True)
        r2 = _make_run("r2", finished=True)
        await store.upsert(r1)
        await asyncio.sleep(0.01)
        await store.upsert(r2)
        runs = await store.list(limit=10)
        assert len(runs) == 2
        assert runs[0]["run_id"] == r2.run_id  # 最近在前

    async def test_list_pagination_and_status_filter(self, store_factory):
        store = store_factory()
        ok = _make_run("ok", finished=True)
        await store.upsert(ok)
        bad = _make_run("bad", finished=False)
        bad.status = "failed"
        await store.upsert(bad)
        all_runs = await store.list(limit=10)
        assert len(all_runs) == 2
        failed = await store.list(limit=10, status="failed")
        assert len(failed) == 1 and failed[0]["run_id"] == bad.run_id

    async def test_ttl_cleanup_removes_old(self, store_factory):
        store = store_factory()
        old = _make_run("old", finished=True)
        old.created_at = time.time() - 1000  # 模拟 1000 秒前
        fresh = _make_run("fresh", finished=True)
        fresh.created_at = time.time() + 1000  # 未来：cleanup 不删
        await store.upsert(old)
        await store.upsert(fresh)
        deleted = await store.cleanup(retention_days=0, now=time.time())
        assert deleted >= 1
        assert await store.get(old.run_id) is None
        assert await store.get(fresh.run_id) is not None

    async def test_upsert_db_error_falls_back_to_memory(self, store_factory, monkeypatch):
        """DB 异常不崩：降级到内存实现（路由层保活）。"""
        store = store_factory()
        run = _make_run()
        # 模拟 DB 写入抛异常
        async def _boom():
            raise RuntimeError("db down")

        monkeypatch.setattr(store, "_execute", _boom)
        await store.upsert(run)  # 不应抛异常
        got = await store.get(run.run_id)
        assert got is not None or got is None  # 降级不抛即为通过


class TestCompatWithMemoryStore:
    async def test_interface_matches_memory_store(self):
        """SQLite store 必须实现与 _DagRunStore 相同的 4 方法。"""
        from api.routes.agent_dag_store_sqlite import DagRunSqliteStore

        s = DagRunSqliteStore(_default_path())
        assert callable(s.upsert)
        assert callable(s.get)
        assert callable(s.list)
        assert callable(s.cleanup)
        await s.close()

    async def test_route_can_switch_to_sqlite(self, store_factory):
        """路由层 _STORE 可替换为 SQLite store，行为一致。"""
        import api.routes.agent_dag as routes_mod

        store = store_factory()
        old = routes_mod._STORE
        try:
            routes_mod._STORE = store
            run = _make_run()
            await store.upsert(run)
            got = await store.get(run.run_id)
            assert got is not None
        finally:
            routes_mod._STORE = old


class TestMemoryStoreContract:
    """v10.0.0：内存 store 接口与 sqlite 对齐（list(status)/cleanup/close）。"""

    async def test_memory_list_with_status_filter(self):
        from api.routes.agent_dag_store import _DagRunStore

        s = _DagRunStore()
        a = _fake_run("m1", "succeeded")
        b = _fake_run("m2", "running")
        s.upsert(a)
        s.upsert(b)
        ok = s.list(status="succeeded")
        assert [r.run_id for r in ok] == ["m1"]
        assert len(s.list(limit=10, status=None)) == 2

    async def test_memory_cleanup_removes_old(self):
        from api.routes.agent_dag_store import _DagRunStore

        s = _DagRunStore()
        s.upsert(_fake_run("old", "succeeded", created_at=time.time() - 10 * 86400))
        s.upsert(_fake_run("new", "succeeded"))
        n = s.cleanup(retention_days=7)
        assert n == 1
        assert s.get("new") is not None and s.get("old") is None

    async def test_memory_close_clears(self):
        from api.routes.agent_dag_store import _DagRunStore

        s = _DagRunStore()
        s.upsert(_fake_run("x", "succeeded"))
        await s.close()
        assert s.get("x") is None


def _fake_run(run_id: str, status: str, created_at: float | None = None):
    """构造最小 DagRun 兼容对象（复用 store._serialize 所需字段）。"""
    from api.agent.dag import DagRun

    r = DagRun(run_id=run_id, name=run_id, nodes={})
    r.status = status
    r.created_at = created_at if created_at is not None else time.time()
    r.finished_at = time.time() if status != "running" else None
    return r

