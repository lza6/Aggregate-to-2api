"""tests/test_dag_resume.py — v13 P0-7 DAG 节点轨迹持久化 + 幂等续跑。

覆盖：
- 引擎层 execute_run(resume=True) 幂等续跑：中途 failed 的 run → 终态 succeeded，
  已 succeeded 节点不重跑（计数器断言，attempt 保留原值）
- 轨迹回调 on_trace：每节点终态收敛一条快照（含 status/result/error/attempt/duration/condition）
- SQLite store 持久化：node_traces 表写入 → 重启 store 实例仍可查（GET 回填 traces）
- HTTP 端点：POST /v1/agent/dag/{run_id}/resume
  - IF_DAG_RESUME_ENABLED=0（缺省）→ 404
  - 无 Key 公益开放（guard_chat_request）
  - run 不存在 → 404

付费红线：引擎层注入 Mock executor；HTTP 层 TestClient 用内存 store（不碰真实付费上游）。
"""

from __future__ import annotations

import os
import tempfile
import time

import pytest

os.environ.setdefault("IF_AGENT_DAG_ENABLED", "1")
os.environ.setdefault("IF_AGENT_PLANNER_ENABLED", "1")
os.environ.setdefault("IF_MOCK_UPSTREAM", "1")
os.environ.setdefault("IF_DB_FILE", "data/test-dag-resume.db")
os.environ.setdefault("IF_ACCOUNT_AUTO", "0")
os.environ.setdefault("IF_MOCK_REGISTER", "1")
os.environ.setdefault("IF_REQUESTS_PER_MINUTE", "0")
# HTTP 用例用独立内存 store（避免与持久化用例争 data/dag_runs.db）
os.environ.setdefault("IF_DAG_STORE_BACKEND", "memory")
os.environ.setdefault("IF_DAG_STORE_DB", "data/test-dag-resume-runs.db")


def _make_node(id_: str, depends_on=None, kind: str = "llm"):
    from api.agent.dag import DagNode

    return DagNode(id=id_, kind=kind, depends_on=depends_on or [])


# ── 引擎层：execute_run 幂等续跑 ─────────────────────────────
async def _fail_exec(node_id: str, state: dict) -> str:
    raise RuntimeError("always fail")


async def _ok_exec(node_id: str, state: dict) -> str:
    return "ok"


class TestExecuteRunResume:
    async def test_resume_reaches_succeeded_and_skips_done(self):
        """链式 A→B→C 中途 B failed（C 被 fail_fast skipped）→ resume → 终态 succeeded。

        计数器断言：首次 A=1,B=1,C=0（C skipped）；resume 只重跑 B/C（A 已 succeeded 不重跑），
        B 重跑成功（calls B=2）、C 依赖恢复后重跑成功（calls C=1）。
        """
        from api.agent.dag import build_graph, execute_run

        nodes = [_make_node("A"), _make_node("B", ["A"]), _make_node("C", ["B"])]
        run = build_graph("resume-test", nodes, max_parallel=3, fail_fast=True, retry=0)

        calls: dict[str, int] = {}

        async def _exec(node_id: str, state: dict) -> str:
            calls[node_id] = calls.get(node_id, 0) + 1
            if node_id == "B" and calls["B"] == 1:
                raise RuntimeError("injected fail on first B")
            return f"ok-{node_id}"

        await execute_run(run, _exec)
        assert run.status == "failed"
        assert run.nodes["A"].status == "succeeded"
        assert run.nodes["B"].status == "failed"
        assert run.nodes["C"].status == "skipped"
        assert calls == {"A": 1, "B": 1}

        # resume：A 已 succeeded 不重跑（calls["A"] 保持 1）；B/C 重置后重跑且成功
        await execute_run(run, _exec, resume=True)
        assert run.status == "succeeded"
        assert run.nodes["B"].status == "succeeded"
        assert run.nodes["C"].status == "succeeded"
        assert calls == {"A": 1, "B": 2, "C": 1}
        # 已 succeeded 节点 A 的 attempt 保留原值（未被重置）
        assert run.nodes["A"].attempt == 1

    async def test_resume_idempotent_when_all_succeeded(self):
        """全 succeeded 的 run resume → 不重跑任何节点（计数器不变）。"""
        from api.agent.dag import build_graph, execute_run

        nodes = [_make_node("A"), _make_node("B", ["A"])]
        run = build_graph("resume-idem", nodes, max_parallel=2, fail_fast=True, retry=0)

        calls: dict[str, int] = {}

        async def _exec(node_id: str, state: dict) -> str:
            calls[node_id] = calls.get(node_id, 0) + 1
            return f"ok-{node_id}"

        await execute_run(run, _exec)
        assert run.status == "succeeded"
        before = dict(calls)

        await execute_run(run, _exec, resume=True)
        assert calls == before  # 无任何节点重跑
        assert run.status == "succeeded"

    async def test_resume_resets_failed_attempt(self):
        """failed 节点 resume → attempt 归零重算（重试耗尽后 reset 再首跑成功）。"""
        from api.agent.dag import build_graph, execute_run

        nodes = [_make_node("A")]
        run = build_graph("resume-attempt", nodes, max_parallel=1, fail_fast=True, retry=2)

        n = run.nodes["A"]
        await execute_run(run, _fail_exec)
        assert n.status == "failed"
        assert n.attempt == 3  # 初始 1 + 重试 2

        await execute_run(run, _ok_exec, resume=True)
        assert run.nodes["A"].status == "succeeded"
        assert run.nodes["A"].attempt == 1  # 已重置归零后首跑成功


# ── 引擎层：节点终态轨迹回调 ────────────────────────────────
class TestNodeTraceCallback:
    async def test_trace_collected_per_terminal_state(self):
        """on_trace 在每个节点终态（succeeded/failed/skipped）被回调一次，快照字段齐全。"""
        from api.agent.dag import build_graph, execute_run

        nodes = [_make_node("A"), _make_node("B", ["A"])]
        run = build_graph("trace-test", nodes, max_parallel=2, fail_fast=True, retry=0)

        traces: list[dict] = []

        async def _on_trace(trace: dict) -> None:
            traces.append(trace)

        async def _exec(node_id: str, state: dict) -> str:
            if node_id == "B":
                raise RuntimeError("B boom")
            return f"ok-{node_id}"

        await execute_run(run, _exec, on_trace=_on_trace)

        assert len(traces) == 2
        by_id = {t["node_id"]: t for t in traces}
        a = by_id["A"]
        b = by_id["B"]
        assert a["status"] == "succeeded"
        assert a["result"] == "ok-A"
        assert a["error"] is None
        assert a["attempt"] == 1
        assert a["duration_ms"] >= 0
        assert a["condition"] is None
        assert a["run_id"] == run.run_id
        assert a["finished_at"] is not None
        assert b["status"] == "failed"
        assert "B boom" in (b["error"] or "")

    async def test_trace_callback_exception_does_not_break_execution(self):
        """回调抛异常不破坏节点执行（轨迹增强能力失败仅 warning）。"""
        from api.agent.dag import build_graph, execute_run

        nodes = [_make_node("A")]
        run = build_graph("trace-fail", nodes)

        async def _boom(trace: dict) -> None:
            raise RuntimeError("trace handler boom")

        async def _exec(node_id: str, state: dict) -> str:
            return "ok"

        await execute_run(run, _exec, on_trace=_boom)
        assert run.status == "succeeded"
        assert run.nodes["A"].status == "succeeded"


# ── SQLite store：节点轨迹持久化 ─────────────────────────────
def _default_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def _make_run_for_store(name: str = "轨迹测试", *, finished: bool = False):
    from api.agent.dag import build_graph

    nodes = [
        _make_node("A"),
        _make_node("B", ["A"]),
    ]
    run = build_graph(name, nodes, max_parallel=2, fail_fast=True, retry=0)
    run.mark_running()
    for nid in ("A",):
        run.nodes[nid].mark_succeeded("ok-A")
    run.nodes["B"].mark_failed("boom")
    if finished:
        run.mark_finished()
    return run


class TestStoreNodeTraces:
    async def test_trace_persists_and_survives_restart(self):
        """node_traces 写入 → 关闭 → 新 store 实例（模拟重启）读回仍可查。"""
        from api.routes.agent_dag_store_sqlite import DagRunSqliteStore

        path = _default_path()
        store1 = DagRunSqliteStore(path)
        run = _make_run_for_store(finished=True)
        await store1.upsert(run)
        await store1.append_trace(
            {
                "run_id": run.run_id,
                "node_id": "A",
                "status": "succeeded",
                "result": "ok-A",
                "error": None,
                "attempt": 1,
                "duration_ms": 12.0,
                "condition": None,
                "finished_at": time.time(),
            }
        )
        await store1.append_trace(
            {
                "run_id": run.run_id,
                "node_id": "B",
                "status": "failed",
                "result": None,
                "error": "boom",
                "attempt": 1,
                "duration_ms": 3.0,
                "condition": None,
                "finished_at": time.time(),
            }
        )
        await store1.close()

        store2 = DagRunSqliteStore(path)
        got = await store2.get(run.run_id)
        assert got is not None
        assert got["status"] == "failed"
        by_id = {n["id"]: n for n in got["nodes"]}
        assert by_id["A"]["traces"], "节点 A 应有轨迹快照"
        assert by_id["A"]["traces"][0]["status"] == "succeeded"
        assert by_id["A"]["traces"][0]["result"] == "ok-A"
        assert by_id["B"]["traces"], "节点 B 应有轨迹快照"
        assert by_id["B"]["traces"][0]["error"] == "boom"
        await store2.close()

    async def test_trace_persisted_without_restart(self):
        """同一 store 实例 upsert 后（未重启）get 即可查轨迹。"""
        from api.routes.agent_dag_store_sqlite import DagRunSqliteStore

        path = _default_path()
        store = DagRunSqliteStore(path)
        run = _make_run_for_store(finished=True)
        await store.upsert(run)
        await store.append_trace(
            {
                "run_id": run.run_id,
                "node_id": "A",
                "status": "succeeded",
                "result": "ok-A",
                "error": None,
                "attempt": 1,
                "duration_ms": 5.0,
                "condition": None,
                "finished_at": time.time(),
            }
        )
        got = await store.get(run.run_id)
        by_id = {n["id"]: n for n in got["nodes"]}
        assert len(by_id["A"]["traces"]) == 1
        assert by_id["A"]["traces"][0]["status"] == "succeeded"
        await store.close()


# ── HTTP 端点：POST /v1/agent/dag/{run_id}/resume ────────────
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_dag_store():
    """每用例清 DAG run store（内存 store 进程级，防跨用例残留串扰）。"""
    from api.routes.agent_dag import _STORE

    _clear = getattr(_STORE, "clear", None) or getattr(_STORE, "close", None)
    if _clear:
        try:
            _clear()
        except Exception:
            pass


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


def _seed_failed_run(client, name: str, store_backend: str = "memory"):
    """构造一个可续跑的中途 failed run（内存 store：DagRun 对象直接标 failed）。

    首次全链路（HTTP 提交→后台执行→终态）用真实 Mock executor 完成 succeeded 后，
    人为把 B 节点标 failed（内存对象直接改），模拟"上次运行 B 失败"状态——resume
    端点对内存 store 操作的就是同一 DagRun 对象，续跑路径合法且可复现。
    """
    from api.agent.dag import build_graph
    from api.routes.agent_dag import _STORE

    nodes = [_make_node("A"), _make_node("B", ["A"]), _make_node("C", ["A"])]
    run = build_graph(name, nodes, max_parallel=3, fail_fast=True, retry=0)
    # 先跑全成功（真实 executor Mock 上游）
    _STORE.upsert(run)

    from api.routes.agent_dag import _execute_run_safe, _store_trace_callback

    async def _back():
        await _execute_run_safe(run, on_trace=_store_trace_callback)

    # 同步测试无 running loop：本用例仅需"内存 store 已有该 DagRun 对象"，
    # 直接同步执行引擎（注入 ok executor）即可得到与后台任务相同的终态。
    import asyncio

    _loop = asyncio.new_event_loop()
    try:
        _loop.run_until_complete(_back())
    finally:
        _loop.close()
    _wait_run_finished(client, run.run_id)
    _STORE.upsert(run)
    # 人为标记 B failed、A 保持 succeeded（resume 前快照）
    run.nodes["B"].mark_failed("injected fail before resume")
    run.nodes["B"].started_at = run.nodes["B"].started_at or time.time()
    run.mark_running()
    return run


class TestDagResumeEndpoint:
    def test_resume_disabled_default_404(self, client):
        """IF_DAG_RESUME_ENABLED 缺省 0 → resume 端点 404（开关关闭即拒绝）。"""
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

    def test_resume_after_failed_run_returns_succeeded(self, client):
        """中途标记 failed 的 run → resume → 终态 succeeded，且已 succeeded 节点不重跑。"""
        os.environ["IF_DAG_RESUME_ENABLED"] = "1"
        from api.config import reset_settings

        reset_settings()
        try:
            run = _seed_failed_run(client, "http-resume")
            assert run.status == "running"
            assert run.nodes["A"].status == "succeeded"
            assert run.nodes["B"].status == "failed"

            r = client.post(f"/v1/agent/dag/{run.run_id}/resume")
            assert r.status_code == 200, f"resume 应 200: {r.status_code} {r.text[:300]}"
            body = r.json()
            assert body["run_id"] == run.run_id
            assert body["resumed"] is True
            assert body["status"] in ("running", "pending")

            final = _wait_run_finished(client, run.run_id)
            assert final["status"] == "succeeded"
            node_map = {n["id"]: n for n in final["nodes"]}
            assert node_map["B"]["status"] == "succeeded"
            assert node_map["A"]["status"] == "succeeded"
            # 幂等：已 succeeded 节点 attempt 保留原值（首次执行 attempt=1）
            assert node_map["A"]["attempt"] == 1
        finally:
            os.environ.pop("IF_DAG_RESUME_ENABLED", None)
            reset_settings()

    def test_resume_missing_run_404(self, client):
        os.environ["IF_DAG_RESUME_ENABLED"] = "1"
        from api.config import reset_settings

        reset_settings()
        try:
            r = client.post("/v1/agent/dag/no-such-run/resume")
            assert r.status_code == 404
        finally:
            os.environ.pop("IF_DAG_RESUME_ENABLED", None)
            reset_settings()
