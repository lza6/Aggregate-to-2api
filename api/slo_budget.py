"""B1 黄金信号 + SLO 错误预算引擎（30 天滚动窗口）。

SRE 标准错误预算语义：
- 预算 = 1 - target（如 99% 成功率 → 1% 错误预算）
- 消耗 = max(0, target - actual) / budget（实际错误率超目标时消耗预算）
- budget_remaining_pct = max(0, 100 - 消耗率×100)
- status：≥50% 预算 → green，1%-50% → yellow，≤0% → red

4 类 SLO（30 天滚动窗口）：
- request_success_rate：请求成功率，目标 ≥ 99%（total_images / total_requests）
- p95_latency：P95 端到端时延（ms），目标 ≤ 30000ms（用 stats 的 avg_duration 估算，
  无 P95 直方图时用 2×avg 近似 P95）
- queue_wait_p95：队列等待 P95（ms），目标 ≤ 5000ms（slow_log 的 queue_ms_p95 优先；
  无则用 queued/queue_capacity 比率估算）
- solve_success_rate：求解成功率（窗口），目标 ≥ 95%（solver_guard snapshot 的
  window_success_rate）

设计约束：不 import slow_log/solver_guard 的模块实例（避免循环依赖），由调用方
（health.py）传 snapshot dict。engine_snapshot 的 queued/queue_capacity 仅在
queue_wait_p95 缺乏 slow_log 数据时作为 fallback 估算输入。
"""

from __future__ import annotations

from typing import Any, Literal

# SLO 状态：绿/黄/红
SLOStatus = Literal["green", "yellow", "red"]

# 默认滚动窗口（30 天）
_DEFAULT_WINDOW_DAYS = 30

# SLO 目标与阈值（ms）
_TARGET_REQUEST_SUCCESS = 0.99  # 请求成功率 ≥ 99%
_TARGET_P95_LATENCY_MS = 30_000.0  # P95 端到端 ≤ 30s
_TARGET_QUEUE_WAIT_P95_MS = 5_000.0  # 队列等待 P95 ≤ 5s
_TARGET_SOLVE_SUCCESS = 0.95  # 求解成功率 ≥ 95%

# P95 估算系数：无直方图时用 avg × k 近似 P95
_P95_FROM_AVG_FACTOR = 2.0

# 队列等待估算：无 slow_log 时按 (queued/capacity) × 阈值线性映射（满载即触阈）
_QUEUE_RATIO_TO_MS_SCALE = _TARGET_QUEUE_WAIT_P95_MS


class SLOBudgetEngine:
    """SLO 错误预算引擎：聚合 stats_overview + solver_snapshot + slow_stats 计算 4 类 SLO。

    纯函数式（无内部状态）——每次 snapshot 基于传入的快照 dict 实时计算，
    避免与 DB/全局单例耦合及循环依赖。
    """

    def __init__(self, window_days: int = _DEFAULT_WINDOW_DAYS) -> None:
        self.window_days = max(1, int(window_days))

    # ── 单个 SLO 计算 ──────────────────────────────
    @staticmethod
    def _status_from_remaining(remaining_pct: float) -> SLOStatus:
        """预算剩余百分比 → 状态：≥50% green，1%-50% yellow，≤0% red。"""
        if remaining_pct >= 50.0:
            return "green"
        if remaining_pct >= 1.0:
            return "yellow"
        return "red"

    @staticmethod
    def _compute_budget_higher_better(
        target: float,
        actual: float | None,
    ) -> tuple[float | None, float, SLOStatus]:
        """越高越好的 SLO（成功率）：SRE 标准错误预算。

        - actual 为 None（无数据）→ 视为满预算（green，不惩罚冷启动）。
        - actual >= target → 未消耗预算 → green。
        - actual < target → 消耗率 = (target - actual) / (1 - target)，
          budget_remaining_pct = max(0, 100 - 消耗率×100)。
        """
        if actual is None:
            return None, 100.0, "green"
        if actual >= target:
            return actual, 100.0, "green"
        budget = max(1e-9, 1.0 - target)  # 错误预算（防除零）
        consumed = max(0.0, target - actual) / budget
        remaining_pct = max(0.0, 100.0 - consumed * 100.0)
        return actual, remaining_pct, SLOBudgetEngine._status_from_remaining(remaining_pct)

    @staticmethod
    def _compute_budget_lower_better(
        threshold: float,
        actual: float | None,
    ) -> tuple[float | None, float, SLOStatus]:
        """越低越好的阈值型 SLO（时延/队列等待）：余头比率模型。

        budget_remaining_pct = max(0, 1 - actual/threshold) × 100
        - actual 为 None → 满预算（green，不惩罚无数据）。
        - actual <= threshold → 未触阈 → green。
        - actual > threshold → 按超出比例消耗，映射到 yellow/red。
        """
        if actual is None:
            return None, 100.0, "green"
        threshold_safe = max(1e-9, float(threshold))
        headroom = max(0.0, 1.0 - float(actual) / threshold_safe)
        remaining_pct = headroom * 100.0
        return actual, remaining_pct, SLOBudgetEngine._status_from_remaining(remaining_pct)

    @staticmethod
    def _aggregate_status(statuses: list[SLOStatus]) -> SLOStatus:
        """整体状态：任一 red → red；任一 yellow → yellow；全 green → green。"""
        if "red" in statuses:
            return "red"
        if "yellow" in statuses:
            return "yellow"
        return "green"

    # ── 主入口：snapshot ────────────────────────────
    def snapshot(
        self,
        stats_overview: dict[str, Any] | None,
        solver_snapshot: dict[str, Any] | None,
        slow_stats: dict[str, Any] | None = None,
        engine_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """计算 4 类 SLO 的错误预算快照。

        Args:
            stats_overview: db.stats_overview() 返回的 dict，含 total_requests /
                total_images / total_errors / avg_duration_sec。
            solver_snapshot: solver_guard.snapshot() 返回的 dict，含 window_success_rate。
            slow_stats: 可选，slow_log.stats() 增强后的 dict，含 queue_ms_p95。
                若无 queue_ms_p95 字段则回退到 engine_snapshot 估算。
            engine_snapshot: 可选，engine.snapshot() 返回的 dict，含 queued /
                queue_capacity（用于 queue_wait_p95 fallback 估算）。

        Returns:
            {window_days, overall_status, slos: {name: {target, actual,
            budget_remaining_pct, status, unit}}}
        """
        stats = stats_overview or {}
        ssnap = solver_snapshot or {}
        slow = slow_stats or {}
        esnap = engine_snapshot or {}

        # ── 1. 请求成功率 ──
        total_req = int(stats.get("total_requests") or 0)
        total_img = int(stats.get("total_images") or 0)
        req_rate = (total_img / total_req) if total_req > 0 else None
        req_actual, req_remain, req_status = self._compute_budget_higher_better(_TARGET_REQUEST_SUCCESS, req_rate)

        # ── 2. P95 端到端时延 ──
        avg_sec = stats.get("avg_duration_sec")
        avg_sec_f = float(avg_sec) if avg_sec is not None else None
        if avg_sec_f is not None:
            p95_ms = avg_sec_f * 1000.0 * _P95_FROM_AVG_FACTOR
        else:
            p95_ms = None
        _, p95_remain, p95_status = self._compute_budget_lower_better(_TARGET_P95_LATENCY_MS, p95_ms)

        # ── 3. 队列等待 P95 ──
        queue_p95_ms: float | None = None
        # 优先用 slow_log 的 queue_ms_p95
        q_p95_raw = slow.get("queue_ms_p95")
        if q_p95_raw is not None:
            try:
                queue_p95_ms = float(q_p95_raw)
            except (TypeError, ValueError):
                queue_p95_ms = None
        # fallback：无 slow_log 数据时用 queued/capacity 比率线性映射
        if queue_p95_ms is None:
            queued = int(esnap.get("queued") or 0)
            capacity = int(esnap.get("queue_capacity") or 0)
            if capacity > 0:
                ratio = max(0.0, min(1.0, queued / capacity))
                queue_p95_ms = ratio * _QUEUE_RATIO_TO_MS_SCALE
        _, queue_remain, queue_status = self._compute_budget_lower_better(_TARGET_QUEUE_WAIT_P95_MS, queue_p95_ms)

        # ── 4. 求解成功率（窗口）──
        win_rate = ssnap.get("window_success_rate")
        win_rate_f: float | None
        if win_rate is not None:
            try:
                win_rate_f = float(win_rate)
            except (TypeError, ValueError):
                win_rate_f = None
        else:
            win_rate_f = None
        solve_actual, solve_remain, solve_status = self._compute_budget_higher_better(_TARGET_SOLVE_SUCCESS, win_rate_f)

        slos: dict[str, dict[str, Any]] = {
            "request_success_rate": {
                "target": _TARGET_REQUEST_SUCCESS,
                "actual": round(req_actual, 4) if req_actual is not None else None,
                "budget_remaining_pct": round(req_remain, 2),
                "status": req_status,
                "unit": "ratio",
            },
            "p95_latency": {
                "target": _TARGET_P95_LATENCY_MS,
                "actual": round(p95_ms, 1) if p95_ms is not None else None,
                "budget_remaining_pct": round(p95_remain, 2),
                "status": p95_status,
                "unit": "ms",
            },
            "queue_wait_p95": {
                "target": _TARGET_QUEUE_WAIT_P95_MS,
                "actual": round(queue_p95_ms, 1) if queue_p95_ms is not None else None,
                "budget_remaining_pct": round(queue_remain, 2),
                "status": queue_status,
                "unit": "ms",
            },
            "solve_success_rate": {
                "target": _TARGET_SOLVE_SUCCESS,
                "actual": round(solve_actual, 4) if solve_actual is not None else None,
                "budget_remaining_pct": round(solve_remain, 2),
                "status": solve_status,
                "unit": "ratio",
            },
        }

        overall = self._aggregate_status([req_status, p95_status, queue_status, solve_status])

        return {
            "window_days": self.window_days,
            "overall_status": overall,
            "slos": slos,
        }


# ── 模块级单例（health.py 直接引用）───────
slo_budget = SLOBudgetEngine()
