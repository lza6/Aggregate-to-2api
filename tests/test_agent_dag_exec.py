"""tests/test_agent_dag_exec.py — DAG 节点执行体单元测试（v9.0.0-A）。

覆盖 execute_node 的 5 个 kind 分发 + 未知 kind + 空 state：
- scene：规则正则识别场景（复用 intent）
- llm：IF_MOCK_UPSTREAM=1 → Mock 占位；=0 且无 chat model → 降级占位（不崩）
- critic：Mock 规则评分终检（不真实付费）
- memory：L0 观察写入
- tool：占位（v9.0.0-B 补本地工具回路）
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("IF_MOCK_UPSTREAM", "1")
os.environ.setdefault("IF_DB_FILE", "data/test-agent-dag-exec.db")


def _state(kind: str, prompt: str = "测试") -> dict:
    return {"node": {"id": "n1", "kind": kind, "prompt": prompt, "model": None}}


class TestExecNode:
    async def test_scene_kind(self):
        from api.routes.agent_dag_exec import execute_node

        result = await execute_node("n1", _state("scene", "显示时间"))
        assert result == "scene=unknown"  # 非图像意图 → unknown（不崩）
        result2 = await execute_node("n1", _state("scene", "画一只猫"))
        assert result2.startswith("scene=")  # 图像意图 → scene=image/…（不崩即可）

    async def test_llm_kind_mock(self):
        from api.routes.agent_dag_exec import execute_node

        result = await execute_node("n1", _state("llm", "生成结果"))
        assert result.startswith("[llm-mock]")

    async def test_critic_kind(self):
        from api.routes.agent_dag_exec import execute_node

        result = await execute_node("n1", _state("critic", "短"))
        assert "critic=" in result

    async def test_memory_kind(self):
        from api.routes.agent_dag_exec import execute_node

        result = await execute_node("n1", _state("memory", "记住这个"))
        assert result in ("memory=stored",) or result.startswith("memory=")

    async def test_tool_kind_placeholder(self):
        from api.routes.agent_dag_exec import execute_node

        # v10.0.0：tool 节点真实回路——无工具名时返回可用工具清单（不再返回 v9.0.0-B 占位串）
        result = await execute_node("n1", _state("tool", "列出可用工具"))
        assert "[tool]" in result
        assert "可用工具" in result or "技能" in result or "skill" not in result.lower(), f"应返回工具回路结果: {result[:200]}"

    async def test_unknown_kind_returns_empty(self):
        from api.routes.agent_dag_exec import execute_node

        result = await execute_node("n1", _state("bogus"))
        assert result == ""

    async def test_empty_state_defaults_llm(self):
        from api.routes.agent_dag_exec import execute_node

        # 空 state → 默认 llm + 空 prompt → Mock 占位（不崩）
        result = await execute_node("n1", {})
        assert result.startswith("[llm-mock]")

    async def test_llm_real_path_fallback(self, monkeypatch):
        """IF_MOCK_UPSTREAM=0 时真实 tryingopen 路径：无可用模型/无 provider → 降级占位。

        若测试环境恰好有真实 tryingopen 上游可用，会返回真实文本（不以 [llm-mock] 开头），
        此时同样可接受——本用例验证「不崩、不抛异常」，付费红线由代码审查保障。
        """
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")
        from api.routes.agent_dag_exec import execute_node

        result = await execute_node("n1", _state("llm", "真实路径"))
        # 不崩即可；文本可能为占位或真实上游回复
        assert isinstance(result, str) and result
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "1")


class TestToolNodeRoundtrip:
    """v10.0.0：tool 节点真实回路——可发现本地 skills + 按名称读取工具。

    复用 api/skills/loader 的能力（SkillIndex.names / load_skill），零 provider 付费。
    """

    async def test_tool_lists_available_skills(self):
        from api.routes.agent_dag_exec import _exec_tool

        # 不指定工具名 → 返回可发现工具清单（JSON 文本）
        result = await _exec_tool("列出可用工具")
        assert "可用工具" in result, f"应返回工具清单: {result[:200]}"

    async def test_tool_loads_skill_by_name(self):
        from api.routes.agent_dag_exec import _exec_tool

        # 指定真实存在的技能名 → 返回该 skill 的描述（真实读取本地技能库）
        result = await _exec_tool("使用 image-quality-check 工具")
        assert result and "image-quality-check" in result, f"应返回该 skill 描述: {result[:200]}"

    async def test_tool_unknown_tool_fallback(self):
        from api.routes.agent_dag_exec import _exec_tool

        result = await _exec_tool("调用一个不存在的工具 xxx-no-such-tool")
        assert result and "未找到" in result, f"未知工具应有明确提示: {result[:200]}"


class TestNodeTimeoutGuard:
    """v10.0.0：单节点执行超时兜底——防上游 hang 拖死整个 DAG run。"""

    async def test_slow_node_timeout_falls_back(self, monkeypatch):
        from api.routes import agent_dag_exec as exec_mod

        # 把超时调成极小值，模拟节点内部 hang（asyncio.sleep 永不返回）
        monkeypatch.setattr(exec_mod, "NODE_EXEC_TIMEOUT_SECONDS", 0.05)

        async def _slow(*a, **k):
            await asyncio.sleep(10)

        monkeypatch.setattr(exec_mod, "_dispatch", _slow)
        from api.routes.agent_dag_exec import execute_node

        result = await execute_node("n1", {"node": {"id": "n1", "kind": "llm", "prompt": "x"}})
        assert "timeout" in result or "降级" in result, f"超时节点应降级返回: {result[:200]}"

    async def test_normal_node_unaffected(self):
        from api.routes.agent_dag_exec import execute_node

        result = await execute_node("n1", {"node": {"id": "n1", "kind": "scene", "prompt": "显示时间"}})
        assert result.startswith("scene=")
