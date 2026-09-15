"""tests/test_agent_tool_guard.py — P1-8 工具调用循环安全护栏测试。

验收（计划 P1-8）：
- 破坏性工具名（rm -rf /、git reset --hard、DELETE FROM accounts 等）→
  `_exec_tool` 返回明确拒绝文本，不执行（PreToolUse 硬门禁）
- LLM 工具循环提取到破坏性工具名 → 快速拒绝（不回调 provider、不进 skills 索引执行）
- `IF_BUDGET_GUARD_MODE=enforce` + 预算不足（默认 0）→ 真实工具调用返回
  BUDGET_EXCEEDED/402 拒绝文本
- 默认 off 模式 → 零行为变化（工具正常加载 / 清单 / 未知提示）

付费红线：registry 全程 monkeypatch / 本地技能索引，零真实上游调用。
"""

from __future__ import annotations

import importlib

import pytest

# 破坏性命令样本（对齐 api/agent/guard.py _DESTRUCTIVE_PATTERNS）
_DESTRUCTIVE_SAMPLES = [
    "调用 rm -rf /",
    "执行 git reset --hard",
    "git push --force origin main",
    "DELETE FROM accounts",
    "DROP TABLE imagefree.db",
]


def _exec_tool(prompt: str) -> str:
    from api.routes.agent_dag_exec import _exec_tool as fn

    return __import__("asyncio").run(fn(prompt))


class TestToolDestructiveGuard:
    @pytest.mark.parametrize("prompt", _DESTRUCTIVE_SAMPLES)
    def test_exec_tool_rejects_destructive_commands(self, prompt):
        """破坏性命令样本 → 明确拒绝文本，不执行。"""
        result = _exec_tool(prompt)
        assert "拒绝执行" in result, f"应返回拒绝文本: {result[:200]}"
        assert "已加载技能" not in result, "破坏性命令不得进入技能加载路径"
        assert "可用工具" not in result, "破坏性命令不得返回工具清单"

    def test_exec_tool_normal_tool_still_works(self):
        """默认 off 模式：真实技能名 → 正常加载（零回归）。"""
        result = _exec_tool("使用 image-quality-check 工具")
        assert "已加载技能" in result, f"正常工具应加载: {result[:200]}"

    def test_exec_tool_listing_still_works(self):
        """默认 off 模式：列举请求 → 返回工具清单（零回归）。"""
        result = _exec_tool("列出可用工具")
        assert "可用工具" in result, f"列举应返回清单: {result[:200]}"

    def test_exec_tool_unknown_tool_still_fallback(self):
        """默认 off 模式：未知工具 → 明确未找到（零回归）。"""
        result = _exec_tool("调用一个不存在的工具 xxx-no-such-tool")
        assert "未找到" in result, f"未知工具应有提示: {result[:200]}"


class TestToolNodeKindGuard:
    def test_tool_node_rejects_destructive(self):
        """execute_node 的 tool 节点同样过硬门禁（不执行破坏性命令）。"""
        from api.routes.agent_dag_exec import execute_node

        result = __import__("asyncio").run(execute_node("n1", {"node": {"kind": "tool", "prompt": "调用 rm -rf /"}}))
        assert "拒绝执行" in result, f"tool 节点应拒绝破坏性命令: {result[:200]}"


class TestLLMToolLoopGuard:
    """T2 工具循环破坏性快速拒绝（复用 v12.0.1 _patch_registry_provider 范式）。"""

    def test_llm_loop_fast_rejects_destructive_tool(self, monkeypatch):
        """LLM 响应含 [tool:rm -rf /] → 快速拒绝，不再回调 provider 第二轮。"""
        from api.config import reset_settings
        from api.routes.agent_dag_exec import _exec_llm

        reg_mod = importlib.import_module("api.providers.registry")

        class _Provider:
            def __init__(self):
                self.calls: list[list[dict]] = []

            async def chat_collect(self, model_id, messages, **kw):
                self.calls.append(messages)
                return {"text": "我需要先执行 [tool:rm -rf /]"}

        class _Registry:
            def __init__(self, p):
                self._p = p

            def all_chat_models(self):
                return [type("M", (), {"id": "tryingopen/t1"})()]

            chat_providers = property(lambda self: {"tryingopen": self._p})

        p = _Provider()
        monkeypatch.setattr(reg_mod, "registry", _Registry(p))
        monkeypatch.setattr(reg_mod, "bootstrap", lambda: None)
        monkeypatch.delenv("IF_MOCK_UPSTREAM", raising=False)
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")
        monkeypatch.setenv("IF_LLM_TOOL_ITERATIONS", "2")
        reset_settings()

        out = __import__("asyncio").run(_exec_llm("执行清理"))
        assert "拒绝执行" in out, f"应返回拒绝文本: {out[:200]}"
        assert len(p.calls) == 1, "破坏性工具应快速拒绝，不再发起第二轮 LLM 调用"

    def test_llm_loop_normal_tool_still_loops(self, monkeypatch):
        """非破坏性工具 → 正常执行并回填第二轮（零回归）。"""
        from api.config import reset_settings
        from api.routes.agent_dag_exec import _exec_llm

        reg_mod = importlib.import_module("api.providers.registry")

        class _Provider:
            def __init__(self):
                self.calls: list[list[dict]] = []

            async def chat_collect(self, model_id, messages, **kw):
                self.calls.append(messages)
                n = len(self.calls)
                if n == 1:
                    return {"text": "我先查技能 [tool:image-quality-check]"}
                return {"text": "最终答案：已完成"}

        class _Registry:
            def __init__(self, p):
                self._p = p

            def all_chat_models(self):
                return [type("M", (), {"id": "tryingopen/t1"})()]

            chat_providers = property(lambda self: {"tryingopen": self._p})

        p = _Provider()
        monkeypatch.setattr(reg_mod, "registry", _Registry(p))
        monkeypatch.setattr(reg_mod, "bootstrap", lambda: None)
        monkeypatch.delenv("IF_MOCK_UPSTREAM", raising=False)
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")
        monkeypatch.setenv("IF_LLM_TOOL_ITERATIONS", "2")
        reset_settings()

        out = __import__("asyncio").run(_exec_llm("生成主图"))
        assert "最终答案" in out
        assert len(p.calls) == 2, "正常工具应循环二轮"


class TestToolBudgetGuard:
    def test_budget_enforce_blocks_real_tool_call(self, monkeypatch):
        """IF_BUDGET_GUARD_MODE=enforce + 预算未配置(0) → 工具调用返回 402 拒绝文本。"""
        from api.config import reset_settings

        monkeypatch.delenv("IF_BUDGET_GUARD_MODE", raising=False)
        monkeypatch.setenv("IF_BUDGET_GUARD_MODE", "enforce")
        monkeypatch.delenv("IF_COST_BUDGET_USD", raising=False)
        monkeypatch.setenv("IF_COST_BUDGET_USD", "0")
        reset_settings()
        try:
            result = _exec_tool("使用 image-quality-check 工具")
        finally:
            reset_settings()
        assert "BUDGET_EXCEEDED" in result, f"enforce 超预算应拒绝: {result[:200]}"
        assert "402" in result, f"拒绝文本应含 402 语义: {result[:200]}"
        assert "已加载技能" not in result, "enforce 超预算不得执行工具"

    def test_budget_enforce_listing_not_blocked(self, monkeypatch):
        """enforce 模式下列举请求仍可用（本地零成本，不拦）。"""
        from api.config import reset_settings

        monkeypatch.delenv("IF_BUDGET_GUARD_MODE", raising=False)
        monkeypatch.setenv("IF_BUDGET_GUARD_MODE", "enforce")
        monkeypatch.delenv("IF_COST_BUDGET_USD", raising=False)
        monkeypatch.setenv("IF_COST_BUDGET_USD", "0")
        reset_settings()
        try:
            result = _exec_tool("列出可用工具")
        finally:
            reset_settings()
        assert "可用工具" in result, f"列举不应被预算拦截: {result[:200]}"

    def test_budget_observe_does_not_block(self, monkeypatch):
        """observe 模式超限仅 warning，不拦截（工具正常执行）。"""
        from api.config import reset_settings

        monkeypatch.delenv("IF_BUDGET_GUARD_MODE", raising=False)
        monkeypatch.setenv("IF_BUDGET_GUARD_MODE", "observe")
        monkeypatch.delenv("IF_COST_BUDGET_USD", raising=False)
        monkeypatch.setenv("IF_COST_BUDGET_USD", "0")
        reset_settings()
        try:
            result = _exec_tool("使用 image-quality-check 工具")
        finally:
            reset_settings()
        assert "已加载技能" in result, f"observe 模式应放行: {result[:200]}"
