"""B1 黄金信号 + SLO 错误预算看板验收测试。

验证 `deploy/api/slo_budget.py` 的 SLOBudgetEngine：
- snapshot 返回结构含 window_days / overall_status / slos（4 类 SLO）
- 故障样本消耗预算 → status 恶化为 yellow/red
- 高成功率样本 → budget_remaining_pct 接近 100，status=green
- /v1/healthz 输出含 slo_budget 块
"""
from __future__ import annotations

import pytest


def _base_stats(total: int, images: int, errors: int, avg_duration: float | None) -> dict:
    """构造 stats_overview 形状的 dict。"""
    return {
        "total_requests": total,
        "total_images": images,
        "total_errors": errors,
        "avg_duration_sec": avg_duration,
    }


def _base_solver_snapshot(rate: float | None) -> dict:
    """构造 solver_guard.snapshot() 形状的 dict。"""
    return {
        "solve_total": 100,
        "solve_success_total": 95,
        "solve_failure_total": 5,
        "window_success_rate": rate,
        "window_solve_count": 100 if rate is not None else 0,
        "solver_status": "ok",
    }


class TestSLOBudgetShape:
    def test_snapshot_returns_required_keys(self):
        from api.slo_budget import slo_budget

        slo = slo_budget.snapshot(
            _base_stats(1000, 990, 10, 3.0),
            _base_solver_snapshot(0.99),
        )
        assert "window_days" in slo
        assert "overall_status" in slo
        assert "slos" in slo
        assert isinstance(slo["slos"], dict)

    def test_snapshot_has_four_slo_categories(self):
        from api.slo_budget import slo_budget

        slo = slo_budget.snapshot(
            _base_stats(1000, 990, 10, 3.0),
            _base_solver_snapshot(0.99),
        )
        expected = {
            "request_success_rate",
            "p95_latency",
            "queue_wait_p95",
            "solve_success_rate",
        }
        assert set(slo["slos"].keys()) == expected

    def test_each_slo_has_target_actual_budget_status(self):
        from api.slo_budget import slo_budget

        slo = slo_budget.snapshot(
            _base_stats(1000, 990, 10, 3.0),
            _base_solver_snapshot(0.99),
        )
        for name, entry in slo["slos"].items():
            assert "target" in entry, f"{name} 缺 target"
            assert "actual" in entry, f"{name} 缺 actual"
            assert "budget_remaining_pct" in entry, f"{name} 缺 budget_remaining_pct"
            assert "status" in entry, f"{name} 缺 status"
            assert entry["status"] in ("green", "yellow", "red"), f"{name} status 非法: {entry['status']}"


class TestSLOBudgetBehavior:
    def test_budget_decreases_on_failures(self):
        """成功率 0.90 < target 0.99 → budget_remaining_pct < 100，status 为 red 或 yellow。"""
        from api.slo_budget import slo_budget

        slo = slo_budget.snapshot(
            _base_stats(1000, 900, 100, 3.0),
            _base_solver_snapshot(0.90),
        )
        rsr = slo["slos"]["request_success_rate"]
        assert rsr["actual"] is not None
        assert rsr["actual"] < rsr["target"]
        assert rsr["budget_remaining_pct"] < 100
        assert rsr["status"] in ("red", "yellow"), f"故障样本应触发 red/yellow，实得 {rsr['status']}"

    def test_budget_recovers_on_success(self):
        """高成功率 0.999 → budget_remaining_pct 接近 100，status=green。"""
        from api.slo_budget import slo_budget

        slo = slo_budget.snapshot(
            _base_stats(1000, 999, 1, 3.0),
            _base_solver_snapshot(0.999),
        )
        rsr = slo["slos"]["request_success_rate"]
        assert rsr["budget_remaining_pct"] >= 90
        assert rsr["status"] == "green"

    def test_solve_success_rate_red_when_below_target(self):
        """求解成功率 < 95% → status 为 red 或 yellow。"""
        from api.slo_budget import slo_budget

        slo = slo_budget.snapshot(
            _base_stats(1000, 990, 10, 3.0),
            _base_solver_snapshot(0.80),
        )
        ssr = slo["slos"]["solve_success_rate"]
        assert ssr["actual"] is not None
        assert ssr["actual"] < ssr["target"]
        assert ssr["status"] in ("red", "yellow")

    def test_overall_status_red_when_any_slo_red(self):
        """至少一个 SLO 红 → overall_status=red。"""
        from api.slo_budget import slo_budget

        slo = slo_budget.snapshot(
            _base_stats(1000, 500, 500, 3.0),  # 成功率 50% << 99%
            _base_solver_snapshot(0.50),
        )
        assert slo["overall_status"] == "red"

    def test_overall_status_green_when_all_healthy(self):
        from api.slo_budget import slo_budget

        slo = slo_budget.snapshot(
            _base_stats(1000, 999, 1, 3.0),
            _base_solver_snapshot(0.999),
        )
        assert slo["overall_status"] == "green"

    def test_p95_latency_uses_avg_when_no_histogram(self):
        """无 P95 直方图时用 2×avg 近似，超阈值时恶化。"""
        from api.slo_budget import slo_budget

        # avg=20s → 近似 P95≈40s > 30s 阈值 → red
        slo = slo_budget.snapshot(
            _base_stats(1000, 990, 10, 20.0),
            _base_solver_snapshot(0.99),
        )
        p95 = slo["slos"]["p95_latency"]
        assert p95["actual"] is not None
        assert p95["actual"] > p95["target"]
        assert p95["status"] in ("red", "yellow")

    def test_queue_wait_p95_estimate_from_slow_stats(self):
        """slow_stats 提供 queue_ms_p95 时优先使用。"""
        from api.slo_budget import slo_budget

        slow_stats = {"queue_ms_p95": 6000.0}  # 6s > 5s 阈值
        slo = slo_budget.snapshot(
            _base_stats(1000, 990, 10, 3.0),
            _base_solver_snapshot(0.99),
            slow_stats=slow_stats,
        )
        qw = slo["slos"]["queue_wait_p95"]
        assert qw["actual"] is not None
        assert qw["actual"] > qw["target"]
        assert qw["status"] in ("red", "yellow")

    def test_zero_requests_does_not_crash(self):
        """无请求时（分母为 0）应安全返回 None 而非抛异常。"""
        from api.slo_budget import slo_budget

        slo = slo_budget.snapshot(
            _base_stats(0, 0, 0, None),
            _base_solver_snapshot(None),
        )
        rsr = slo["slos"]["request_success_rate"]
        assert rsr["actual"] is None
        assert rsr["budget_remaining_pct"] == 100  # 无数据视为满预算


class TestHealthzSLOBudget:
    @pytest.mark.asyncio
    async def test_healthz_contains_slo_budget(self):
        """/v1/healthz 返回的 dict 含 slo_budget 块。"""
        from api.routes.health import healthz

        h = await healthz()
        assert "slo_budget" in h, "healthz 缺 slo_budget 块"
        slo = h["slo_budget"]
        assert "window_days" in slo
        assert "overall_status" in slo
        assert "slos" in slo
        assert {"request_success_rate", "p95_latency", "queue_wait_p95",
                "solve_success_rate"} <= set(slo["slos"].keys())
