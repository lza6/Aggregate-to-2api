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
