"""tests/test_budget_guard.py — v12.0.0 P1-M11 dispatch 前硬预算门禁测试（TDD）。

覆盖（三态模式 + 估算表 + 红线语义）：
- off 模式（默认）：零行为变化直通
- observe：超限只 warning 不拦截（allowed=True）
- enforce：估算超限 raise BudgetExceededError（402）
- 预算未配置（0）：enforce 拒绝付费 provider、放行免费 provider
- estimate_cost 未知 provider 走保守档
付费红线：本测试零上游调用（花费读取走 chat_usage，测试内 monkeypatch）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.agent.budget_guard import (
    BudgetExceededError,
    assert_can_spend,
    check_can_spend,
    estimate_cost,
)


@pytest.fixture(autouse=True)
def _reset_cfg(monkeypatch):
    """每用例重置 config 工厂（三态模式/预算均走 Settings）。"""
    from api.config import reset_settings

    reset_settings()
    yield
    reset_settings()


@pytest.fixture()
def _no_spent(monkeypatch):
    """把当日花费读取打桩为 0（隔离 chat_usage DB 依赖）。"""
    import api.agent.budget_guard as bg

    async def _zero() -> float:
        return 0.0

    monkeypatch.setattr(bg, "_spent_today_usd", _zero)


class TestEstimate:
    def test_free_provider_zero(self):
        assert estimate_cost("imagefree") == 0.0
        assert estimate_cost("tryingopen") == 0.0

    def test_paid_provider_positive(self):
        assert estimate_cost("falai") > 0.0

    def test_unknown_provider_conservative(self):
        assert estimate_cost("no-such-provider") == 0.01
        assert estimate_cost("") == 0.01


class TestOffMode:
    async def test_off_default_passes(self, _no_spent):
        """默认 off：直通零行为变化。"""
        d = await check_can_spend("falai")
        assert d.allowed is True
        assert d.mode == "off"


class TestObserveMode:
    async def test_observe_over_budget_warns_not_blocks(self, monkeypatch, _no_spent):
        """observe：估算超限 allowed=True（只记录）。"""
        from api.config import reset_settings

        monkeypatch.setenv("IF_BUDGET_GUARD_MODE", "observe")
        monkeypatch.setenv("IF_COST_BUDGET_USD", "0.01")
        reset_settings()
        d = await check_can_spend("falai")  # est 0.04 > budget 0.01
        assert d.allowed is True
        assert d.mode == "observe"
        assert "observe" in d.reason


class TestEnforceMode:
    async def test_enforce_over_budget_raises_402(self, monkeypatch, _no_spent):
        """enforce：估算超限 raise BudgetExceededError（402 语义）。"""
        from api.config import reset_settings

        monkeypatch.setenv("IF_BUDGET_GUARD_MODE", "enforce")
        monkeypatch.setenv("IF_COST_BUDGET_USD", "0.01")
        reset_settings()
        with pytest.raises(BudgetExceededError) as ei:
            await assert_can_spend("falai")
        assert ei.value.status_code == 402

    async def test_enforce_within_budget_passes(self, monkeypatch, _no_spent):
        from api.config import reset_settings

        monkeypatch.setenv("IF_BUDGET_GUARD_MODE", "enforce")
        monkeypatch.setenv("IF_COST_BUDGET_USD", "10.0")
        reset_settings()
        d = await assert_can_spend("falai")
        assert d.allowed is True

    async def test_enforce_budget_unset_blocks_paid_only(self, monkeypatch, _no_spent):
        """预算未配置（0）：enforce 拒付费 provider、放行免费 provider（红线语义）。"""
        from api.config import reset_settings

        monkeypatch.setenv("IF_BUDGET_GUARD_MODE", "enforce")
        monkeypatch.delenv("IF_COST_BUDGET_USD", raising=False)
        reset_settings()
        with pytest.raises(BudgetExceededError):
            await assert_can_spend("falai")
        d = await assert_can_spend("imagefree")  # 免费 provider 放行
        assert d.allowed is True


class TestSpentIntegration:
    async def test_spent_usd_counts_toward_budget(self, monkeypatch):
        """当日花费计入：spent 0.05 + est 0.04 > budget 0.08 → enforce 拒绝。"""
        import api.agent.budget_guard as bg
        from api.config import reset_settings

        async def _spent() -> float:
            return 0.05

        monkeypatch.setattr(bg, "_spent_today_usd", _spent)
        monkeypatch.setenv("IF_BUDGET_GUARD_MODE", "enforce")
        monkeypatch.setenv("IF_COST_BUDGET_USD", "0.08")
        reset_settings()
        with pytest.raises(BudgetExceededError):
            await assert_can_spend("falai")


class TestToolEstimate:
    """P1-9：MCP 工具单次估算（工具/模型维度近似常量表）。"""

    def test_tool_estimate_known(self):
        from api.agent.budget_guard import estimate_tool_cost

        assert estimate_tool_cost("generate_image") == 0.04
        assert estimate_tool_cost("dag_plan") == 0.0
        assert estimate_tool_cost("dag_status") == 0.0
        assert estimate_tool_cost("skills_list") == 0.0

    def test_tool_estimate_unknown_conservative(self):
        from api.agent.budget_guard import estimate_tool_cost

        assert estimate_tool_cost("no-such-tool") == 0.01
        assert estimate_tool_cost("") == 0.01

    def test_tool_estimate_accepts_model_dim(self):
        """model 维度参数预留：当前未细分维度，命中工具档即可。"""
        from api.agent.budget_guard import estimate_tool_cost

        assert estimate_tool_cost("generate_image", model="sdxl") == 0.04


class TestMcpBudgetGuard:
    """P1-9：MCP tools/call 分发前预算门禁（HTTP 真路径，Mock 上游零付费）。

    覆盖：
    - observe：超预算只记录不拦截（返回正常结果）
    - enforce：超预算 tools/call 返回 MCP JSON-RPC 错误 -32000（不抛 500）
    - enforce：预算内正常调用通过
    """

    @staticmethod
    def _enable_mcp(monkeypatch, mode: str, budget: str, spent: float = 0.0):
        """IF_MCP_ENABLED=1 + IF_MOCK_UPSTREAM=1 + 预算三态；mock 当日花费隔离 DB。"""
        import api.agent.budget_guard as bg
        from api.config import reset_settings

        async def _spent() -> float:
            return spent

        monkeypatch.setattr(bg, "_spent_today_usd", _spent)
        monkeypatch.setenv("IF_MCP_ENABLED", "1")
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "1")
        monkeypatch.setenv("IF_BUDGET_GUARD_MODE", mode)
        monkeypatch.setenv("IF_COST_BUDGET_USD", budget)
        reset_settings()

    @staticmethod
    def _rpc(method: str, params: dict | None = None, req_id: int = 1) -> dict:
        body = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            body["params"] = params
        return body

    def test_observe_over_budget_records_not_blocks(self, monkeypatch):
        """observe：当日花费已超预算（spent 0.02 > budget 0.01）→ 不拦截（isError=False），审计已记录。"""
        from api.audit import audit_log
        from api.main import app

        calls: list[tuple[str, str, str]] = []
        monkeypatch.setattr(
            audit_log, "record", lambda action, actor, target, *a, **k: calls.append((action, actor, target))
        )
        self._enable_mcp(monkeypatch, mode="observe", budget="0.01", spent=0.02)
        with TestClient(app) as c:
            resp = c.post(
                "/v1/mcp", json=self._rpc("tools/call", {"name": "generate_image", "arguments": {"prompt": "cat"}})
            )
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is False
        # v16 P0-1：generate_image 返回异步任务契约 {task_id, status: queued}（Mock 下同步产出）
        assert "task_id" in result["content"][0]["text"] and "queued" in result["content"][0]["text"]
        # 审计记录：工具名 + 估算 + decision
        assert any(action == "mcp.tool.call" and target == "generate_image" for action, _actor, target in calls)

    def test_enforce_over_budget_returns_mcp_error_not_500(self, monkeypatch):
        """enforce：当日花费已超预算（spent 0.02 > budget 0.01）→ JSON-RPC 错误 -32000（HTTP 200，不抛 500）。"""
        from api.main import app

        self._enable_mcp(monkeypatch, mode="enforce", budget="0.01", spent=0.02)
        with TestClient(app) as c:
            resp = c.post(
                "/v1/mcp", json=self._rpc("tools/call", {"name": "generate_image", "arguments": {"prompt": "cat"}})
            )
        assert resp.status_code == 200  # JSON-RPC 错误仍走 200 信封，不 500
        body = resp.json()
        assert "error" in body and "result" not in body
        assert body["error"]["code"] == -32000
        assert "Budget exceeded" in body["error"]["message"]

    def test_enforce_within_budget_passes(self, monkeypatch):
        """enforce：预算充足 → dag_plan 正常返回 Mock 规划结果。"""
        from api.main import app

        self._enable_mcp(monkeypatch, mode="enforce", budget="10.0")
        with TestClient(app) as c:
            resp = c.post(
                "/v1/mcp", json=self._rpc("tools/call", {"name": "dag_plan", "arguments": {"prompt": "画一只猫"}})
            )
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is False
        assert '"mock"' in result["content"][0]["text"] or "nodes" in result["content"][0]["text"]
