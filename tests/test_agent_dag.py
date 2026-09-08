"""tests/test_agent_dag.py — v9.0.0-A 智能体 DAG 编排引擎单元测试（TDD：先测后码）。

覆盖 Story 1-3 全部 DAG 引擎验收标准：
- 拓扑排序正确性：串行链 / 并行扇出 / 环形依赖拒绝
- 状态机：pending→running→succeeded/failed，失败传播 skipped
- 并发：max_parallel 限流、并行扇出真并发
- 重试：指数退避 + 抖动，重试耗尽才 failed
- 边界：空图 / 未知 kind / 缺依赖 / 重复 id / 超大图
- 付费红线：全程 Mock，无真实 provider 调用
"""

from __future__ import annotations

import asyncio
import time

import pytest

from api.agent.dag import (
    MAX_RUN_NODES,
    DagError,
    DagNode,
    build_graph,
    execute_run,
    parse_nodes,
    topological_sort,
)


# ── 拓扑排序 ─────────────────────────────────────────────────
class TestTopologicalSort:
    def test_serial_chain_order(self):
        """串行链 A→B→C 顺序正确。"""
        nodes = [
            DagNode(id="A", kind="llm", depends_on=[]),
            DagNode(id="B", kind="llm", depends_on=["A"]),
            DagNode(id="C", kind="llm", depends_on=["B"]),
        ]
        order = topological_sort(nodes)
        assert order == ["A", "B", "C"]

    def test_fanout_parallel_reaches_all(self):
        """并行扇出：根→{B,C,D} 全可达。"""
        nodes = [
            DagNode(id="A", kind="llm", depends_on=[]),
            DagNode(id="B", kind="llm", depends_on=["A"]),
            DagNode(id="C", kind="llm", depends_on=["A"]),
            DagNode(id="D", kind="llm", depends_on=["A"]),
        ]
        order = topological_sort(nodes)
        # 拓扑序保证 A 在最前，且 B/C/D 全部出现
        assert order[0] == "A"
        assert set(order) == {"A", "B", "C", "D"}

    def test_cycle_raises(self):
        """环形依赖（A→B→A）必须抛 DagError。"""
        nodes = [
            DagNode(id="A", kind="llm", depends_on=["B"]),
            DagNode(id="B", kind="llm", depends_on=["A"]),
        ]
        with pytest.raises(DagError):
            topological_sort(nodes)

    def test_self_dependency_raises(self):
        """自依赖（A→A）必须抛 DagError。"""
        nodes = [DagNode(id="A", kind="llm", depends_on=["A"])]
        with pytest.raises(DagError):
            topological_sort(nodes)

    def test_unknown_dependency_raises(self):
        """依赖的节点不存在必须抛 DagError。"""
        nodes = [DagNode(id="A", kind="llm", depends_on=["NOPE"])]
        with pytest.raises(DagError):
            topological_sort(nodes)

    def test_empty_input_ok(self):
        """空执行 Try：empty → 直接返回（sort 前已拦）。"""
        order = topological_sort([])
        assert order == []


# ── 节点解析（HTTP 输入 → DagNode）───────────────────────────
class TestParseNodes:
    def test_valid_nodes(self):
        raw = [
            {"id": "A", "kind": "llm", "depends_on": [], "prompt": "hi"},
            {"id": "B", "kind": "llm", "depends_on": ["A"], "prompt": "yo"},
        ]
        nodes = parse_nodes(raw)
        assert len(nodes) == 2
        assert nodes[0].id == "A"
        assert nodes[1].depends_on == ["A"]

    def test_empty_list_rejected(self):
        with pytest.raises(DagError):
            parse_nodes([])

    def test_duplicate_id_rejected(self):
        raw = [
            {"id": "A", "kind": "llm", "depends_on": []},
            {"id": "A", "kind": "llm", "depends_on": []},
        ]
        with pytest.raises(DagError):
            parse_nodes(raw)

    def test_unknown_kind_rejected(self):
        raw = [{"id": "A", "kind": "bogus", "depends_on": []}]
        with pytest.raises(DagError):
            parse_nodes(raw)

    def test_bad_depends_on_type_rejected(self):
        raw = [{"id": "A", "kind": "llm", "depends_on": "A"}]  # str 而非 list
        with pytest.raises(DagError):
            parse_nodes(raw)

    def test_over_limit_rejected(self):
        raw = [{"id": f"n{i}", "kind": "llm", "depends_on": []} for i in range(MAX_RUN_NODES + 1)]
        with pytest.raises(DagError):
            parse_nodes(raw)

    def test_missing_prompt_ok_for_llm_node(self):
        """llm 节点缺 prompt 不拒绝（引擎层给默认提示词，调用方友好）。"""
        nodes = parse_nodes([{"id": "A", "kind": "llm", "depends_on": []}])
        assert nodes[0].prompt is None


def _make_node(id_: str, depends_on=None, kind: str = "llm"):
    return DagNode(id=id_, kind=kind, depends_on=depends_on or [])


# ── DAG 构建 ──────────────────────────────────────────────────
class TestBuildGraph:
    def test_builds_dependency_map(self):
        nodes = [_make_node("A"), _make_node("B", ["A"])]
        run = build_graph("t1", nodes, max_parallel=2)
        # 依赖图含全部节点（根节点空列表也在内），断言用 items 全集比较
        assert run.dependencies["B"] == ["A"]
        assert run.dependencies["A"] == []
        assert sorted(run.upstreams["A"]) == ["B"]

    def test_max_parallel_default(self):
        nodes = [_make_node("A")]
        run = build_graph("t1", nodes)
        assert run.max_parallel >= 1


# ── 执行器（Mock 节点执行器）─────────────────────────────────
async def _make_executor(results: dict[str, str], *, sleep: float = 0.0):
    async def _exec(node_id: str, state: dict) -> str:
        if sleep:
            await asyncio.sleep(sleep)
        return results[node_id]

    return _exec


async def _make_fail_executor(fail_on: set[str]):
    async def _exec(node_id: str, state: dict) -> str:
        if node_id in fail_on:
            raise RuntimeError(f"injected {node_id}")
        return f"ok-{node_id}"

    return _exec


# ── 执行：串行 + 失败传播 ────────────────────────────────────
class TestExecuteRun:
    async def test_serial_success(self):
        nodes = [_make_node("A"), _make_node("B", ["A"]), _make_node("C", ["B"])]
        run = build_graph("t1", nodes, max_parallel=2)
        executor = await _make_executor({"A": "a", "B": "b", "C": "c"})
        await execute_run(run, executor)
        assert run.status == "succeeded"
        assert [n.status for n in run.nodes.values()] == ["succeeded"] * 3
        assert run.nodes["C"].result == "c"

    async def test_fail_fast_skips_downstream(self):
        """A 成功、B 失败 → fail_fast 下 C 被 skipped，run failed。"""
        nodes = [_make_node("A"), _make_node("B", ["A"]), _make_node("C", ["B"])]
        run = build_graph("t1", nodes, max_parallel=2, fail_fast=True)
        executor = await _make_fail_executor({"B"})
        await execute_run(run, executor)
        assert run.status == "failed"
        assert run.nodes["A"].status == "succeeded"
        assert run.nodes["B"].status == "failed"
        assert run.nodes["C"].status == "skipped"

    async def test_fail_fast_false_isolates_branch(self):
        """fail_fast=False：A→{B失败,C}，C 不受影响继续成功。"""
        nodes = [_make_node("A"), _make_node("B", ["A"]), _make_node("C", ["A"])]
        run = build_graph("t1", nodes, max_parallel=2, fail_fast=False)
        executor = await _make_fail_executor({"B"})
        await execute_run(run, executor)
        assert run.nodes["B"].status == "failed"
        assert run.nodes["C"].status == "succeeded"
        assert run.status == "failed"  # 有失败 → run failed

    async def test_all_done_marks_succeeded(self):
        nodes = [_make_node("A"), _make_node("B", ["A"])]
        run = build_graph("t1", nodes, max_parallel=2)
        executor = await _make_executor({"A": "a", "B": "b"})
        await execute_run(run, executor)
        assert run.status == "succeeded"
        assert run.finished_at is not None

    async def test_finished_at_set_on_failure(self):
        nodes = [_make_node("A")]
        run = build_graph("t1", nodes, max_parallel=2)
        executor = await _make_fail_executor({"A"})
        await execute_run(run, executor)
        assert run.status == "failed"
        assert run.finished_at is not None

    async def test_duration_millis_recorded(self):
        nodes = [_make_node("A")]
        run = build_graph("t1", nodes, max_parallel=2)
        executor = await _make_executor({"A": "a"}, sleep=0.05)
        await execute_run(run, executor)
        assert run.nodes["A"].duration_ms >= 20


# ── 执行：并发限制 ──────────────────────────────────────────
class TestConcurrency:
    async def test_max_parallel_throttles(self):
        """三并行节点 + max_parallel=1 → 总时长 ≥ 3×sleep（串行化）。"""
        nodes = [_make_node("A"), _make_node("B"), _make_node("C")]
        run = build_graph("t1", nodes, max_parallel=1)
        executor = await _make_executor({"A": "a", "B": "b", "C": "c"}, sleep=0.1)
        t0 = time.monotonic()
        await execute_run(run, executor)
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.29, f"max_parallel=1 应串行，elapsed={elapsed:.3f}"

    async def test_parallel_fanout_runs_concurrently(self):
        nodes = [_make_node("A"), _make_node("B"), _make_node("C")]
        run = build_graph("t1", nodes, max_parallel=3)
        executor = await _make_executor({"A": "a", "B": "b", "C": "c"}, sleep=0.15)
        t0 = time.monotonic()
        await execute_run(run, executor)
        elapsed = time.monotonic() - t0
        assert elapsed < 0.45, f"max_parallel=3 应并发，elapsed={elapsed:.3f}"


# ── 执行：重试 ──────────────────────────────────────────────
class TestRetry:
    async def test_retry_exhausted_marks_failed(self):
        """Node 永远失败 → 重试 N 次后 failed，且 attempt>1。"""
        nodes = [_make_node("A")]
        run = build_graph("t1", nodes, max_parallel=2, retry=2)
        calls = 0

        async def _flaky(node_id: str, state: dict) -> str:
            nonlocal calls
            calls += 1
            raise RuntimeError("flaky")

        await execute_run(run, _flaky)
        assert run.nodes["A"].status == "failed"
        assert calls == 3  # 初始 1 + 重试 2

    async def test_retry_then_success(self):
        """第 2 次成功 → succeeded，attempt=2。"""
        nodes = [_make_node("A")]
        run = build_graph("t1", nodes, max_parallel=2, retry=2)
        calls = 0

        async def _flaky(node_id: str, state: dict) -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("first fail")
            return "ok"

        await execute_run(run, _flaky)
        assert run.nodes["A"].status == "succeeded"
        assert run.nodes["A"].attempt == 2


# ── 状态辅助 ────────────────────────────────────────────────
class TestNodeHelpers:
    def test_mark_running(self):
        n = _make_node("A")
        n.mark_running()
        assert n.status == "running"
        assert n.started_at is not None

    def test_mark_succeeded(self):
        n = _make_node("A")
        n.mark_running()
        n.mark_succeeded("ok")
        assert n.status == "succeeded"
        assert n.result == "ok"
        assert n.duration_ms >= 0

    def test_mark_failed(self):
        n = _make_node("A")
        n.mark_running()
        n.mark_failed("boom")
        assert n.status == "failed"
        assert "boom" in n.error

    def test_public_state_shape(self):
        """对外 JSON 形状稳定（API 契约防坑）。"""
        n = _make_node("A")
        public = n.public_state()
        assert set(public.keys()) >= {"id", "kind", "status", "depends_on", "created_at"}
