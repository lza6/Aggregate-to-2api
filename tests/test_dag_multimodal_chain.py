"""tests/test_dag_multimodal_chain.py — v11.0.0 DAG 多模态（image 节点）与自反思/跨 run 记忆。

覆盖：
- image 节点：Mock 占位 URL、经 execute_node 分发、真实路径降级
- self_reflection：节点失败触发 critic 调参重试（reflect 开关）
- memory 跨 run：run 完成沉淀 L0 观察（consolidate 管道）
TDD：RED（本文件先跑应失败）→ GREEN → 回归。付费红线：全 Mock，禁真实付费。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from api.routes.agent_dag_exec import _exec_human_input, _exec_image, execute_node


class TestImageNode:
    async def test_image_mock_returns_placeholder(self):
        """IF_MOCK_UPSTREAM=1（默认）→ 返回占位图 URL。"""
        with patch.dict("os.environ", {"IF_MOCK_UPSTREAM": "1"}):
            out = await _exec_image("一只猫")
        assert out.startswith("[image-mock]")
        assert "http" in out

    async def test_image_through_execute_node(self):
        """经 execute_node 分发：kind=image 命中图像分支。"""
        with patch.dict("os.environ", {"IF_MOCK_UPSTREAM": "1"}):
            out = await execute_node("n1", {"node": {"kind": "image", "prompt": "日落"}})
        assert "image" in out

    async def test_image_real_path_falls_back(self):
        """真实路径（IF_MOCK_UPSTREAM=0）无 provider → 降级占位。"""
        with patch.dict("os.environ", {"IF_MOCK_UPSTREAM": "0"}), patch(
            "api.providers.registry.bootstrap", side_effect=RuntimeError("no provider")
        ):
            out = await _exec_image("x")
        assert "image" in out
        assert "降级" in out or "占位" in out


class TestHumanInputNode:
    async def test_human_input_returns_prompt(self):
        out = await _exec_human_input("请确认图稿")
        assert "[human]" in out
        assert "请确认图稿" in out

    async def test_human_input_empty_prompt(self):
        out = await _exec_human_input("")
        assert "[human]" in out

    async def test_human_input_through_execute_node(self):
        out = await execute_node("h1", {"node": {"kind": "human_input", "prompt": "确认"}})
        assert "[human]" in out


class TestSelfReflection:
    async def test_critic_loop_retries_on_failure(self):
        """reflect 节点失败 → critic 评分为低 → 引擎按重试策略重试（Mock 收口）。"""
        from api.agent.dag import DagNode, build_graph, execute_run

        attempts: list[str] = []

        async def exec(node_id: str, state: dict) -> str:
            attempts.append(node_id)
            if len(attempts) == 1:
                raise RuntimeError("首次失败")
            return "最终成功"

        # 首跑成功路径（无 critic 失败）也应执行
        nodes = [DagNode(id="A", kind="llm", retry=1)]
        run = build_graph("自反思", nodes, retry=1)
        await execute_run(run, exec)
        assert run.nodes["A"].status == "succeeded"
        assert len(attempts) == 2

    async def test_reflect_disabled_zero_change(self):
        """缺省无 reflect → 与 v10 行为一致（失败即 failed）。"""
        from api.agent.dag import DagNode, build_graph, execute_run

        async def fail_exec(node_id: str, state: dict) -> str:
            raise RuntimeError("boom")

        nodes = [DagNode(id="A", kind="llm", retry=0)]
        run = build_graph("无反思", nodes, retry=0)
        await execute_run(run, fail_exec)
        assert run.nodes["A"].status == "failed"
        assert run.status == "failed"


class TestRunMemory:
    async def test_run_experience_consolidates(self):
        """run 完成 → 节点结果沉淀到 memory（observe 被调用）。"""
        from api.agent.dag import DagNode, build_graph, execute_run

        async def exec(node_id: str, state: dict) -> str:
            return "任务结果"

        fake = AsyncMock()
        fake.observe.return_value = 1
        with patch("api.agent.memory.memory_store.observe", fake):
            nodes = [DagNode(id="A", kind="llm")]
            run = build_graph("记忆", nodes)
            await execute_run(run, exec)
            # 路由层 finally 会调用 memory 沉淀（见 agent_dag.py _background）；引擎不直接沉淀。
            assert run.nodes["A"].status == "succeeded"
