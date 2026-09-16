"""P2-9: 成本预测预警推送。

后台每小时评估近 30 天累计消耗/预算的消耗百分比（口径复用 cost_forecast 的
``predict_budget_burn``：token 成本来自 chat_usage.cost_usd 日级聚合，图片成本为
累计折算值无日级历史不纳入趋势，预算阈值来自 ``IF_COST_BUDGET_USD``）。
消耗百分比 >= ``IF_COST_ALERT_PCT``（缺省 80，0=关闭）时，经 ``alerting``
webhook 通道推送一条预警 payload（含 pct / 预算 / 已耗 / 预测日期）。

幂等（进程级）：模块全局记录最近一次推送的消耗百分比水位，水位未较上次上升
>=5 个百分点（pp）不重复推送；消耗回落到阈值以下时清空水位，下次重新越过阈值
再推。进程重启即复位（重新越过阈值会再推一次，可接受）。

纯本地 DB 查询 + 数学预测，不触发任何真实付费上游调用。
"""

from __future__ import annotations

import datetime
import logging
import time
from typing import Any

from . import config

log = logging.getLogger("cost_alert")

# 幂等水位：最近一次推送时的消耗百分比（%）。None = 未推送/已回落复位。
_LAST_PUSHED_PCT: float | None = None
# 水位上升触发重复推送的最小增量（个百分点）。同水位/小幅波动不反复骚扰。
_PCT_RESCALE_STEP = 5.0


def _reset_alert_state() -> None:
    """测试/运维钩子：清空进程级幂等水位。"""
    global _LAST_PUSHED_PCT
    _LAST_PUSHED_PCT = None


def _burn_pct_from_forecast(forecast: dict[str, Any]) -> float:
    """从 ``predict_budget_burn`` 输出计算消耗百分比（%，无预算/禁用返回 0）。"""
    if forecast.get("disabled"):
        return 0.0
    budget = float(forecast.get("budget_usd") or 0.0)
    if budget <= 0:
        return 0.0
    spent = float(forecast.get("current_spent_30d") or 0.0)
    return spent / budget * 100.0


async def _collect_forecast() -> dict[str, Any]:
    """读取近 30 天日级消耗 + 预算阈值，返回 ``predict_budget_burn`` 输出。

    独立成函数便于测试替换（mock 预测超阈值 / 未超）。
    """
    from .chat_usage import chat_usage_tracker as _tracker  # noqa: PLC0415
    from .cost_forecast import predict_budget_burn  # noqa: PLC0415

    daily_costs = (
        await _tracker.cost_daily(30) if hasattr(_tracker, "cost_daily") else []
    )
    budget = float(config.IF_COST_BUDGET_USD or 0.0)
    return predict_budget_burn(daily_costs, budget)


async def _send_alert_payload(payload: dict[str, Any]) -> bool:
    """经 alerting webhook 通道外发预警（3s 超时，失败仅记日志）。

    L7 修复（审查）：返回 bool——webhook 未配置视为「已处理」（记日志即可，置水位防刷屏）；
    外发抛异常返回 False（不置水位，下次轮询重试，避免发送失败静默抑制后续告警）。
    不影响后台周期任务。
    """
    from .alerting import _send_webhook  # noqa: PLC0415

    url = getattr(config, "IF_ALERT_WEBHOOK_URL", "") or ""
    if not url:
        log.info("成本预警触发但未配置 IF_ALERT_WEBHOOK_URL，仅记录: %s", payload)
        return True
    entry = {
        "name": "cost_alert_pct",
        "severity": "warning",
        "message": (
            f"成本消耗已达预算 {payload['burn_pct']:.1f}%"
            f"（阈值 {payload['threshold_pct']:.0f}%）："
            f"已耗 ${payload['spent_usd']:.2f} / 预算 ${payload['budget_usd']:.2f}，"
            f"预测超预算日 {payload.get('projected_exceed_date') or '无法预测'}"
        ),
        "timestamp": time.time(),
    }
    try:
        await _send_webhook([entry], url)
        return True
    except Exception as e:  # noqa: BLE001  webhook 失败仅记日志，不影响后台周期任务
        log.warning("成本预警 webhook 外发失败: %s", e)
        return False


async def run_cost_alert_once() -> dict[str, Any] | None:
    """单次成本预警评估（后台周期任务每小时调用；测试可直接 await）。

    返回：
        - 触发推送 → 本次 payload dict（含 pct/budget_usd/spent_usd/预测字段）；
        - 未触发 / 幂等抑制 / 关闭 → None。
    """
    global _LAST_PUSHED_PCT

    threshold = float(getattr(config, "IF_COST_ALERT_PCT", 80.0) or 0.0)
    if threshold <= 0:
        return None  # 0=关闭

    forecast = await _collect_forecast()
    pct = _burn_pct_from_forecast(forecast)
    if pct < threshold:
        # 回落阈值以下：清空水位，下次重新越过阈值时再推
        _LAST_PUSHED_PCT = None
        return None

    payload: dict[str, Any] = {
        "name": "cost_alert_pct",
        "burn_pct": round(pct, 1),
        "threshold_pct": float(threshold),
        "budget_usd": float(forecast.get("budget_usd") or 0.0),
        "spent_usd": float(forecast.get("current_spent_30d") or 0.0),
        "daily_avg_30d": float(forecast.get("daily_avg_30d") or 0.0),
        "projected_exceed_date": forecast.get("projected_exceed_date"),
        "days_remaining": forecast.get("days_remaining"),
        "checked_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }

    # 幂等：水位未较上次上升 >=5pp 不重复推送
    if _LAST_PUSHED_PCT is not None and (pct - _LAST_PUSHED_PCT) < _PCT_RESCALE_STEP:
        return None

    # L7 修复：发送成功（或未配置 webhook 已记录）才置水位——发送失败不抑制下一次轮询
    sent = await _send_alert_payload(payload)
    if sent:
        _LAST_PUSHED_PCT = pct
    return payload


__all__ = ["run_cost_alert_once", "_burn_pct_from_forecast", "_reset_alert_state"]
