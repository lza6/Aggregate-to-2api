"""P3-D3: 成本预算燃烧预测。

基于 chat_usage 近 30 天日级 cost_usd 历史，按当前日均消耗速率预测何时超出
IF_COST_BUDGET_USD 阈值。纯本地 DB 查询 + 数学预测，不调用付费 API，不修改
DB schema，不改现有 cost_summary 逻辑。

口径说明（与 /v1/cost 保持一致）：
- token 成本来自 chat_usage.cost_usd 列（按 day 聚合）；
- 图片成本为号池累计积分折算值（account_pool.cost_summary.total_credits_used
  × IF_USD_PER_CREDIT），无日级历史，无法做趋势预测，故不纳入本预测；
- 预算阈值 IF_COST_BUDGET_USD=0 时关闭预测（disabled=True）。
"""

from __future__ import annotations

import datetime
import time
from typing import Any

# 滚动窗口天数（与 daily_avg_30d 口径一致；缺失天视为 0 消耗）
_FORECAST_WINDOW_DAYS = 30


def predict_budget_burn(
    daily_costs: list[dict[str, Any]],
    budget_usd: float,
    *,
    now: float | None = None,
) -> dict[str, Any]:
    """根据近 30 天日级消耗历史预测超预算日期。

    参数：
        daily_costs: ``chat_usage.cost_daily(30)`` 返回的列表，每项含
            ``day``/``cost_usd``/``calls``。允许为空列表（无消耗历史）。
        budget_usd: 预算阈值（来自 ``IF_COST_BUDGET_USD``）。<=0 时关闭预测。
        now: 当前时间戳（测试注入）；缺省取 ``time.time()``。

    返回字段（前端 P3-D3 直接消费）：
        - ``daily_avg_30d``：近 30 天日均消耗（USD，30 天分母；缺失天视为 0）。
        - ``projected_exceed_date``：按当前速率预测的超预算日期（``YYYY-MM-DD``）；
          无消耗历史或预算关闭时为 ``None``。
        - ``days_remaining``：从今天起还能花多少天超预算（小数，1 位）；
          ``None`` 表示无法预测或已关闭。
        - ``budget_usd``：当前预算阈值（原样回传）。
        - ``current_spent_30d``：近 30 天累计消耗（USD）。
        - ``disabled``：是否关闭预测（预算=0）。
        - ``note``：口径与状态说明。

    边界：
        - ``budget_usd <= 0``：``disabled=True``，其余字段仍回传（前端降级展示）。
        - ``daily_avg_30d <= 0``：无消耗历史，``projected_exceed_date=None``。
        - ``current_spent_30d >= budget_usd``：已超预算，``days_remaining=0``，
          ``projected_exceed_date=今天``。
    """
    now_ts = now if now is not None else time.time()
    today = datetime.date.fromtimestamp(now_ts)

    # 30 天分母（缺失天视为 0 消耗），与滚动日均口径一致——避免数据稀疏时日均被高估
    total_30d = sum(float(row.get("cost_usd", 0) or 0) for row in daily_costs)
    current_spent_30d = round(total_30d, 6)
    daily_avg_30d = round(total_30d / float(_FORECAST_WINDOW_DAYS), 6) if total_30d > 0 else 0.0

    if budget_usd <= 0:
        return {
            "daily_avg_30d": daily_avg_30d,
            "projected_exceed_date": None,
            "days_remaining": None,
            "budget_usd": 0.0,
            "current_spent_30d": current_spent_30d,
            "disabled": True,
            "note": "预算未配置（IF_COST_BUDGET_USD=0），不启用燃烧预测。",
        }

    if daily_avg_30d <= 0:
        return {
            "daily_avg_30d": 0.0,
            "projected_exceed_date": None,
            "days_remaining": None,
            "budget_usd": float(budget_usd),
            "current_spent_30d": current_spent_30d,
            "disabled": False,
            "note": "近 30 天无 token 成本消耗历史，无法预测燃烧速率。",
        }

    remaining_budget = float(budget_usd) - current_spent_30d
    if remaining_budget <= 0:
        # 近 30 天累计已超预算阈值
        return {
            "daily_avg_30d": daily_avg_30d,
            "projected_exceed_date": today.strftime("%Y-%m-%d"),
            "days_remaining": 0.0,
            "budget_usd": float(budget_usd),
            "current_spent_30d": current_spent_30d,
            "disabled": False,
            "note": "近 30 天累计消耗已超出预算阈值。",
        }

    days_remaining = remaining_budget / daily_avg_30d
    exceed_date = today + datetime.timedelta(days=days_remaining)
    return {
        "daily_avg_30d": daily_avg_30d,
        "projected_exceed_date": exceed_date.strftime("%Y-%m-%d"),
        "days_remaining": round(days_remaining, 1),
        "budget_usd": float(budget_usd),
        "current_spent_30d": current_spent_30d,
        "disabled": False,
        "note": (
            "预测基于 chat_usage 近 30 天 cost_usd 日级趋势；"
            "图片成本（号池积分折算）为累计值，无日级历史，未纳入趋势预测。"
        ),
    }


__all__ = ["predict_budget_burn"]
