"""api/agent/budget_guard.py — v12.0.0 P1-M11 dispatch 前硬预算门禁。

付费 API 红线代码化（对齐 nexus-llm-router `src/safety/budget.py:8-48 assert_can_spend`）：
真实付费上游调用前估算成本并与预算比较，估算超上限直接拒绝（402 语义），
把"付费上游预算默认 0"从人工遵守变成代码强制。

三态模式（config `if_budget_guard_mode`，缺省 off 零行为变化）：
- off：直通（不估算不拦截）
- observe：估算+记录（超限只 warning，不拦截——上线观察期）
- enforce：估算超限 → raise BudgetExceededError（路由层转 402）

预算口径：`if_cost_budget_usd`（config 现有字段）− 当日已花费
（当月/当日花费从 chat_usage.cost_usd 聚合读取，复用 chat_usage_store，不重复造账本）。

付费红线：本模块自身零上游调用；被守卫的调用方（agent_dag_exec._exec_image 真实路径等）
在 IF_MOCK_UPSTREAM=1 时不经过 enforce（Mock 无成本）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..errors import AppError

log = logging.getLogger("agent.budget_guard")

# 估算表（USD/次；按 provider 定价量级，精确计费走 chat_usage cost_usd 实际记账）
_PROVIDER_ESTIMATE_USD: dict[str, float] = {
    "falai": 0.04,  # fal.ai 按张计费量级
    "imagefree": 0.0,  # 公益免费
    "aifreeforever": 0.0,  # 公益免费
    "nanobanana": 0.0,  # 公益免费
    "tryingopen": 0.0,  # metered 免费
    "unknown": 0.01,  # 保守默认（未知 provider 按低价估）
}


@dataclass(frozen=True)
class BudgetDecision:
    """门禁决策（不可变，供调用方落审计日志）。"""

    allowed: bool
    mode: str  # off / observe / enforce
    estimated_usd: float
    budget_usd: float
    spent_usd: float
    reason: str


class BudgetExceededError(AppError):
    """估算成本超预算（enforce 模式）。路由层应转 402。"""


def _mode() -> str:
    try:
        from ..config import get_settings

        return str(get_settings().if_budget_guard_mode or "off").strip().lower()
    except Exception:
        return "off"


def _budget_usd() -> float:
    try:
        from ..config import get_settings

        return float(get_settings().if_cost_budget_usd or 0.0)
    except Exception:
        return 0.0


async def _spent_today_usd() -> float:
    """当日已花费（chat_usage.cost_usd 当日聚合）。读取失败按 0（fail-open 观察不拦真实用户）。"""
    try:
        from ..chat_usage import chat_usage_tracker

        stats = await chat_usage_tracker.stats("24h")
        return float(stats.get("today_cost_usd", 0.0) or 0.0)
    except Exception as exc:
        log.warning("budget_guard 读取当日花费失败（按 0 计）: %s", exc)
        return 0.0


def estimate_cost(provider: str) -> float:
    """单次调用成本估算（USD）。未知 provider 保守按 unknown 档。"""
    return _PROVIDER_ESTIMATE_USD.get(str(provider or "unknown").strip().lower(), _PROVIDER_ESTIMATE_USD["unknown"])


async def check_can_spend(provider: str) -> BudgetDecision:
    """dispatch 前预算门禁：估算 + 三态决策。

    off → allowed=True（零开销直通）
    observe → 超限只 warning（allowed=True，reason 标 observe_block）
    enforce → 超限 raise BudgetExceededError（402）
    """
    mode = _mode()
    estimated = estimate_cost(provider)
    budget = _budget_usd()

    if mode == "off":
        return BudgetDecision(True, "off", estimated, budget, 0.0, "guard off")
    if budget <= 0.0:
        # 预算未配置：enforce 模式下按"预算 0 红线"拒绝付费 provider（免费 provider 放行）
        if mode == "enforce" and estimated > 0.0:
            return BudgetDecision(False, mode, estimated, 0.0, 0.0, "budget unset; paid provider blocked")
        if mode == "observe" and estimated > 0.0:
            log.warning("budget_guard[observe]: 付费 provider %s 估算 $%.4f，预算未配置", provider, estimated)
        return BudgetDecision(True, mode, estimated, budget, 0.0, "budget unset")

    spent = await _spent_today_usd()
    over = (spent + estimated) > budget + 1e-9
    if over:
        if mode == "enforce":
            return BudgetDecision(False, mode, estimated, budget, spent, f"spent ${spent:.4f} + est ${estimated:.4f} > budget ${budget:.4f}")
        log.warning(
            "budget_guard[observe]: 估算超限 provider=%s spent=%.4f est=%.4f budget=%.4f（不拦截）",
            provider, spent, estimated, budget,
        )
        return BudgetDecision(True, mode, estimated, budget, spent, "observe: over budget (not blocked)")
    return BudgetDecision(True, mode, estimated, budget, spent, "within budget")


async def assert_can_spend(provider: str) -> BudgetDecision:
    """enforce 语义入口：超限抛 BudgetExceededError（402），否则返回决策。

    调用方（真实付费上游 dispatch 前）：
        decision = await assert_can_spend(provider)
    off/observe 模式永不抛（observe 只 warning）；enforce 超限抛。
    """
    decision = await check_can_spend(provider)
    if not decision.allowed:
        raise BudgetExceededError(
            "BUDGET_EXCEEDED",
            f"调用 {provider} 估算 ${decision.estimated_usd:.4f} 超出预算：{decision.reason}",
            402,
        )
    return decision


__all__ = [
    "BudgetDecision",
    "BudgetExceededError",
    "assert_can_spend",
    "check_can_spend",
    "estimate_cost",
]
