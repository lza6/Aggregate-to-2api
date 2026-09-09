"""tests/test_dag_conditional_branch.py — v11.0.0 DAG 条件分支节点。

覆盖：contains/equals 两操作符 true/false 求值、非法表达式 422、缺省不开条件时零行为变化、
依赖终态后条件求值决定 skip、条件为真的下游正常执行。
TDD：RED（本文件先跑应失败）→ GREEN（实现 api/agent/dag.eval_condition）→ 回归。
"""

from __future__ import annotations

import pytest

from api.agent.dag import DagError, DagNode, build_graph, eval_condition, parse_nodes, topological_sort


class TestEvalCondition:
    def test_contains_true(self):
        assert eval_condition("A contains 成功", {"A": {"result": "任务执行成功"}}) is True

    def test_contains_false(self):
        assert eval_condition("A contains 失败", {"A": {"result": "任务执行成功"}}) is False

    def test_equals_true(self):
        assert eval_condition("B equals 完成", {"B": {"result": "完成"}}) is True

    def test_equals_false(self):
        assert eval_condition("B equals 进行中", {"B": {"result": "完成"}}) is False

    def test_missing_dep_raises(self):
        with pytest.raises(DagError):
            eval_condition("X contains 成功", {"A": {"result": "x"}})

    def test_invalid_operator_raises(self):
        with pytest.raises(DagError):
            eval_condition("A regex '.*x'", {"A": {"result": "x"}})

    def test_empty_condition_returns_true(self):
        assert eval_condition(None, {"A": {"result": "x"}}) is True

    def test_number_result_contains(self):
        assert eval_condition("A contains 200", {"A": {"result": 200}}) is True


class TestParseConditionNode:
    def test_condition_field_parses(self):
        nodes = parse_nodes(
            [
                {"id": "A", "kind": "llm", "prompt": "执行"},
                {"id": "B", "kind": "llm", "depends_on": ["A"], "condition": "A contains 成功"},
            ]
        )
        assert nodes[1].condition == "A contains 成功"

    def test_invalid_condition_rejected(self):
        with pytest.raises(DagError):
            parse_nodes(
                [
                    {"id": "A", "kind": "llm"},
                    {"id": "B", "kind": "llm", "depends_on": ["A"], "condition": "A regex 'x'"},
                ]
            )

    def test_condition_operator_not_ending_properly(self):
        with pytest.raises(DagError):
            parse_nodes(
                [
                    {"id": "A", "kind": "llm"},
                    {"id": "B", "kind": "llm", "depends_on": ["A"], "condition": "A 成功"},
                ]
            )

    def test_condition_too_long_rejected(self):
        with pytest.raises(DagError):
            parse_nodes(
                [
                    {"id": "A", "kind": "llm"},
                    {"id": "B", "kind": "llm", "depends_on": ["A"], "condition": "A contains 好" * 200},
                ]
            )


class TestConditionalExecution:
    async def test_condition_true_runs_downstream(self):
        """条件为真 → 下游正常执行。"""
        records: list[str] = []

        async def exec(node_id: str, state: dict) -> str:
            records.append(node_id)
            if node_id == "A":
                return "任务执行成功"
            return "下游执行"

        nodes = [
            DagNode(id="A", kind="llm", prompt="第一步"),
            DagNode(
                id="B", kind="llm", depends_on=["A"], prompt="第二步", condition="A contains 成功"
            ),
        ]
        run = build_graph("条件真", nodes, max_parallel=2, fail_fast=True, retry=0)
        from api.agent.dag import execute_run

        await execute_run(run, exec)
        assert records == ["A", "B"]
        assert run.nodes["A"].status == "succeeded"
        assert run.nodes["B"].status == "succeeded"

    async def test_condition_false_skips_downstream(self):
        """条件为假 → 下游节点 skipped（不执行）。"""
        records: list[str] = []

        async def exec(node_id: str, state: dict) -> str:
            records.append(node_id)
            return "ok"

        nodes = [
            DagNode(id="A", kind="llm", prompt="第一步"),
            DagNode(
                id="B", kind="llm", depends_on=["A"], prompt="第二步", condition="A contains 失败"
            ),
        ]
        run = build_graph("条件假", nodes, max_parallel=2, fail_fast=True, retry=0)
        from api.agent.dag import execute_run

        await execute_run(run, exec)
        assert records == ["A"]
        assert run.nodes["A"].status == "succeeded"
        assert run.nodes["B"].status == "skipped"

    async def test_no_condition_unchanged(self):
        """缺省无条件 → 行为与 v10 完全一致（零回归）。"""
        records: list[str] = []

        async def exec(node_id: str, state: dict) -> str:
            records.append(node_id)
            return "ok"

        nodes = [
            DagNode(id="A", kind="llm"),
            DagNode(id="B", kind="llm", depends_on=["A"]),
        ]
        run = build_graph("无条件", nodes)
        from api.agent.dag import execute_run

        await execute_run(run, exec)
        assert records == ["A", "B"]
        assert run.status == "succeeded"

    def test_condition_node_topology_valid(self):
        nodes = parse_nodes(
            [
                {"id": "A", "kind": "llm"},
                {"id": "B", "kind": "llm", "depends_on": ["A"], "condition": "A contains 成功"},
            ]
        )
        assert topological_sort(nodes) == ["A", "B"]
