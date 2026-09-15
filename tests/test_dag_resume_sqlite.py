"""tests/test_dag_resume_sqlite.py — v14 P2 DAG sqlite 持久化续跑。

覆盖：
- store 层 restore_run：sqlite store 落一个中途 failed 的 run → DagRun 对象
  状态/节点一致（status/attempt/condition/depends_on 全量还原）
- HTTP 端点：sqlite store 后端 run → POST resume → 200 + 终态 succeeded，
  已 succeeded 节点不重跑（attempt 保留原值断言）
- run 不存在 → 404（端点）
- IF_DAG_RESUME_ENABLED=0 → 404（开关关闭即拒绝，既有行为）

付费红线：HTTP 层 TestClient 用 monkeypatch 注入 Mock executor（不触碰真实上游）；
store 层直接注入 Mock executor。零真实付费上游调用。

注意（aiosqlite 跨 loop 陷阱，见 tests/conftest.py）：sqlite store 的 aiosqlite
连接绑定"首次使用它的 loop"。HTTP 用例全部经 TestClient（app portal loop）完成
读写——绝不能在测试内新建事件循环操作 store（会绑到私有 loop，GET/resume 挂死）。
故 HTTP 用例用 monkeypatch._execute_node 全程走 HTTP 链路制造"首轮 B 失败"，
不直接操作 store。
"""

from __future__ import annotations

import os
import tempfile
import time

import pytest

os.environ.setdefault("IF_AGENT_DAG_ENABLED", "1")
os.environ.setdefault("IF_AGENT_PLANNER_ENABLED", "1")
os.environ.setdefault("IF_MOCK_UPSTREAM", "1")
os.environ.setdefault("IF_DB_FILE", "data/test-dag-resume-sqlite.db")
os.environ.setdefault("IF_ACCOUNT_AUTO", "0")
os.environ.setdefault("IF_MOCK_REGISTER", "1")
os.environ.setdefault("IF_REQUESTS_PER_MINUTE", "0")


def _make_node(id_: str, depends_on=None, kind: str = "llm", condition: str | None = None, retry: int = 0):
    from api.agent.dag import DagNode

    return DagNode(id=id_, kind=kind, depends_on=depends_on or [], condition=condition, retry=retry)


def _default_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def _seed_failed_run(store, name: str = "sqlite-resume"):
    """构造一个中途 failed 的 run 并落 sqlite store（A 成功/B 失败/C 条件跳过）。

    状态：A succeeded（result/attempt/duration 完整）、B failed（error 记录）、
    C 依赖条件不成立被 skipped（condition 保留）。模拟"上次运行中断"的可续跑快照。
    """
    from api.agent.dag import build_graph

    nodes = [
        _make_node("A"),
        _make_node("B", ["A"]),
        _make_node("C", ["A"], condition="A contains 成功"),
    ]
    run = build_graph(name, nodes, max_parallel=3, fail_fast=True, retry=1)
    run.mark_running()
    run.nodes["A"].mark_running()
    run.nodes["A"].mark_succeeded("成功-A")
    run.nodes["B"].mark_running()
    run.nodes["B"].mark_failed("injected boom")
    run.nodes["C"].status = "skipped"
    run.nodes["C"].finished_at = time.time()
    run.status = "failed"
    run.finished_at = time.time()
    run.error_summary = "B 执行失败"
    return run


# ── store 层：restore_run 反序列化 ─────────────────────────────
class TestRestoreRun:
    async def test_restore_run_matches_snapshot(self):
        """落库中途 failed 的 run → restore_run → DagRun 状态/节点一致。

        注：dag_runs 表当前只持久化 run 标量列 + nodes_json（不含 fail_fast/
        max_parallel 执行配置），restore 对未持久化字段回退引擎默认值——本用例
        只断言真实持久化内容（run 状态/节点状态/attempt/condition/depends_on）。
        """
        from api.agent.dag import DagRun
        from api.routes.agent_dag_store_sqlite import DagRunSqliteStore

        path = _default_path()
        store = DagRunSqliteStore(path)
        original = _seed_failed_run(store)
        await store.upsert(original)
        await store.close()

        store2 = DagRunSqliteStore(path)
        restored = await store2.restore_run(original.run_id)
        assert restored is not None, "restore_run 应返回 DagRun 对象"
        assert isinstance(restored, DagRun)
        assert restored.run_id == original.run_id
        assert restored.name == original.name
        assert restored.status == "failed"
        assert restored.error_summary == "B 执行失败"
        assert restored.finished_at is not None

        nodes = restored.nodes
        assert set(nodes) == {"A", "B", "C"}
        a = nodes["A"]
        assert a.status == "succeeded"
        assert a.result == "成功-A"
        assert a.attempt == 1
        assert a.depends_on == []
        assert a.condition is None
        b = nodes["B"]
        assert b.status == "failed"
        assert b.error == "injected boom"
        assert b.attempt == 1
        assert b.depends_on == ["A"]
        c = nodes["C"]
        assert c.status == "skipped"
        assert c.condition == "A contains 成功"
        assert c.depends_on == ["A"]
        # 依赖/上游索引还原（续跑路径依赖 dependencies/upstreams）
        assert restored.dependencies == {"A": [], "B": ["A"], "C": ["A"]}
        assert restored.upstreams == {"A": ["B", "C"]}
        await store2.close()

    async def test_restore_run_missing_returns_none(self):
        """不存在的 run_id → restore_run 返回 None。"""
        from api.routes.agent_dag_store_sqlite import DagRunSqliteStore

        store = DagRunSqliteStore(_default_path())
        assert await store.restore_run("no-such-run") is None
        await store.close()

    async def test_restore_run_after_restart_then_resume_succeeds(self):
        """重启 store（跨实例）restore_run → execute_run(resume=True) → 终态 succeeded。

        已 succeeded 节点 A 不重跑（attempt 保留原值），B/C 重置后重跑成功（计数器断言）。
        """
        from api.agent.dag import execute_run
        from api.routes.agent_dag_store_sqlite import DagRunSqliteStore

        path = _default_path()
        store1 = DagRunSqliteStore(path)
        original = _seed_failed_run(store1)
        await store1.upsert(original)
        await store1.close()

        store2 = DagRunSqliteStore(path)
        restored = await store2.restore_run(original.run_id)
        assert restored is not None

        calls: dict[str, int] = {}

        async def _exec(node_id: str, state: dict) -> str:
            calls[node_id] = calls.get(node_id, 0) + 1
            return f"ok-{node_id}"

        await execute_run(restored, _exec, resume=True)
        assert restored.status == "succeeded"
        assert calls == {"B": 1, "C": 1}, "A 已 succeeded 不重跑，仅 B/C 各跑一次"
        assert restored.nodes["A"].status == "succeeded"
        assert restored.nodes["A"].attempt == 1  # 已 succeeded 节点 attempt 保留
        assert restored.nodes["B"].status == "succeeded"
        assert restored.nodes["C"].status == "succeeded"
        await store2.close()


# ── HTTP 端点：sqlite store 后端续跑 ───────────────────────────
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as c:
        yield c


def _wait_run_finished(client, run_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/v1/agent/dag/{run_id}")
        assert r.status_code == 200, f"查询 run 应 200: {r.status_code} {r.text[:300]}"
        body = r.json()
        if body.get("status") in ("succeeded", "failed"):
            return body
        time.sleep(0.3)
    raise AssertionError(f"DAG run {run_id} 在 {timeout}s 内未终态")


def _wait_run_succeeded(client, run_id: str, timeout: float = 30.0) -> dict:
    """等待续跑后终态 succeeded（sqlite 后端续跑期间 DB 仍是旧 failed 快照）。

    resume 后台任务在 execute_run 结束时才 upsert 新终态；此间 GET 读到的是
    旧 failed 快照（非终态竞态）。故续跑验证必须要求最终 == succeeded，而非
    遇到任意终态即返回。
    """
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        r = client.get(f"/v1/agent/dag/{run_id}")
        assert r.status_code == 200, f"查询 run 应 200: {r.status_code} {r.text[:300]}"
        body = r.json()
        last = body
        if body.get("status") == "succeeded":
            return body
        time.sleep(0.3)
    raise AssertionError(f"DAG run {run_id} 在 {timeout}s 内未续跑成功（末态={last.get('status') if last else None}）")


@pytest.fixture
def sqlite_store():
    """独立的 sqlite store（临时 DB 文件）。"""
    from api.routes.agent_dag_store_sqlite import DagRunSqliteStore

    store = DagRunSqliteStore(_default_path())
    yield store
    import asyncio as _aio

    try:
        _aio.new_event_loop().run_until_complete(store.close())
    except Exception:
        pass


@pytest.fixture
def sqlite_backed_store(sqlite_store):
    """把路由层 _STORE 换成 sqlite store，用毕还原（防跨用例串扰其他 DAG 测试文件）。

    注意：store 连接在首次 HTTP 请求（app portal loop）时才打开，全部读写都在
    portal loop 内完成——测试内不得新建事件循环操作该 store（跨 loop 挂死）。
    """
    import api.routes.agent_dag as routes_mod

    old = routes_mod._STORE
    routes_mod._STORE = sqlite_store
    yield sqlite_store
    routes_mod._STORE = old


@pytest.fixture
def failing_first_exec(monkeypatch):
    """monkeypatch _execute_node：首轮 B 失败后恢复正常（续跑成功）的计数器 executor。

    全程在 app portal loop 内执行（经 HTTP 提交/续跑），天然规避 sqlite store
    跨 loop 问题。返回 (calls, state)；首轮 B 抛错，state["fail"]=False 后恢复成功。
    """
    import api.routes.agent_dag as routes_mod

    calls: dict[str, int] = {}
    state = {"fail": True}

    async def _exec(node_id: str, _state: dict) -> str:
        calls[node_id] = calls.get(node_id, 0) + 1
        if state["fail"] and node_id == "B":
            raise RuntimeError("injected fail for seed")
        return f"ok-{node_id}"

    monkeypatch.setattr(routes_mod, "_execute_node", _exec)
    return calls, state


class TestSqliteResumeEndpoint:
    def test_resume_disabled_404(self, client):
        """IF_DAG_RESUME_ENABLED=0 → resume 端点 404（开关关闭即拒绝，既有行为）。"""
        os.environ["IF_DAG_RESUME_ENABLED"] = "0"
        from api.config import reset_settings

        reset_settings()
        try:
            r = client.post("/v1/agent/dag/some-run/resume")
            assert r.status_code == 404
            assert "续跑" in r.text
        finally:
            os.environ.pop("IF_DAG_RESUME_ENABLED", None)
            reset_settings()

    def test_resume_missing_run_404(self, client, sqlite_backed_store):
        """sqlite store 后端：不存在的 run_id → 404（restore_run 为 None）。"""
        os.environ["IF_DAG_RESUME_ENABLED"] = "1"
        from api.config import reset_settings

        reset_settings()
        try:
            r = client.post("/v1/agent/dag/no-such-run/resume")
            assert r.status_code == 404
        finally:
            os.environ.pop("IF_DAG_RESUME_ENABLED", None)
            reset_settings()

    def test_resume_sqlite_run_succeeds(self, client, sqlite_backed_store, failing_first_exec):
        """sqlite store 后端 run → resume → 200 + 终态 succeeded，已 succeeded 节点不重跑。

        全链路经 HTTP：首轮 A→B→C 链中 B 失败（C 因 fail_fast 被 skipped）→ run failed；
        解除注入后 resume → B/C 重跑成功 → 终态 succeeded；计数器断言 A 恰跑 1 次
        （不重跑）、B 首败+重跑共 2 次、C 仅重跑 1 次；A 的 attempt 保留原值。
        """
        os.environ["IF_DAG_RESUME_ENABLED"] = "1"
        from api.config import reset_settings

        reset_settings()
        try:
            calls, state = failing_first_exec

            r = client.post(
                "/v1/agent/dag/run",
                json={
                    "name": "http-sqlite-resume",
                    "nodes": [
                        {"id": "A", "kind": "llm", "depends_on": [], "prompt": "第一"},
                        {"id": "B", "kind": "llm", "depends_on": ["A"], "prompt": "第二"},
                        {"id": "C", "kind": "llm", "depends_on": ["B"], "prompt": "第三"},
                    ],
                },
            )
            assert r.status_code == 200, f"提交应 200: {r.status_code} {r.text[:400]}"
            run_id = r.json()["run_id"]

            first = _wait_run_finished(client, run_id)
            assert first["status"] == "failed"
            node_map = {n["id"]: n for n in first["nodes"]}
            assert node_map["A"]["status"] == "succeeded"
            assert node_map["B"]["status"] == "failed"
            assert node_map["C"]["status"] == "skipped"

            # 首轮 B 失败已定格；解除注入 → 续跑恢复成功
            state["fail"] = False
            rr = client.post(f"/v1/agent/dag/{run_id}/resume")
            assert rr.status_code == 200, f"resume 应 200: {rr.status_code} {rr.text[:300]}"
            assert rr.json()["resumed"] is True

            final = _wait_run_succeeded(client, run_id, timeout=30.0)
            final_map = {n["id"]: n for n in final["nodes"]}
            assert final_map["A"]["status"] == "succeeded"
            assert final_map["B"]["status"] == "succeeded"
            assert final_map["C"]["status"] == "succeeded"
            # 幂等 + 计数器：A 恰跑 1 次（不重跑），B 首败 1 + 续跑 1 = 2，C 仅续跑 1
            assert calls == {"A": 1, "B": 2, "C": 1}, f"执行计数不符: {calls}"
            assert final_map["A"]["attempt"] == 1  # 已 succeeded 节点 attempt 保留原值
        finally:
            os.environ.pop("IF_DAG_RESUME_ENABLED", None)
            reset_settings()
