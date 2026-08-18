"""solver_guard（求解熔断器 + 健康指标）单元测试。

覆盖：成功/失败统计、平均耗时、失败原因分类、滑动窗口成功率、
熔断阈值触发 OPEN、half-open 探测放行、探测成功恢复、连续失败重置。
全部使用独立 SolverGuard 实例（不触碰模块级单例），避免污染服务状态。
"""
import time

import pytest

from api.solver_guard import REASON_CATEGORIES, SolverGuard


# ── 统计 ──────────────────────────────────────────
class TestStats:
    def test_record_success_failure_counts_and_avg(self):
        g = SolverGuard(circuit_threshold=5)
        g.record_success(5.0)
        g.record_success(7.0)
        g.record_failure("timeout", 3.0)
        s = g.snapshot()
        assert s["solve_total"] == 3
        assert s["solve_success_total"] == 2
        assert s["solve_failure_total"] == 1
        assert s["solve_avg_seconds"] == 6.0
        assert s["failure_reasons"] == {"timeout": 1}

    def test_window_success_rate_and_avg(self):
        g = SolverGuard(window_seconds=60)
        g.record_success(1.0)
        g.record_success(1.0)
        g.record_failure("timeout", 2.0)
        s = g.snapshot()
        assert s["window_solve_count"] == 3
        assert s["window_success_rate"] == pytest.approx(2 / 3, abs=1e-4)  # round(...,4)
        assert s["window_avg_seconds"] == pytest.approx(4 / 3, abs=0.01)  # round(...,2)

    def test_window_drops_old_entries(self):
        g = SolverGuard(window_seconds=1.0)
        g.record_success(1.0)
        time.sleep(1.1)
        g.record_failure("timeout", 2.0)
        s = g.snapshot()
        assert s["window_solve_count"] == 1
        assert s["window_success_rate"] == 0.0

    def test_unknown_reason_categorized_other(self):
        g = SolverGuard()
        g.record_failure("bogus_reason")
        assert g.snapshot()["failure_reasons"] == {"other": 1}

    def test_no_solve_yet_returns_none_fields(self):
        g = SolverGuard()
        s = g.snapshot()
        assert s["solve_total"] == 0
        assert s["solve_avg_seconds"] is None
        assert s["window_success_rate"] is None
        assert s["solver_status"] == "ok"

    def test_rejected_total(self):
        g = SolverGuard()
        g.record_rejected()
        g.record_rejected()
        assert g.snapshot()["rejected_total"] == 2

    def test_reason_categories_are_known(self):
        assert set(REASON_CATEGORIES) == {"timeout", "transport", "http_error", "solver_rejected", "other"}


# ── 熔断状态机 ────────────────────────────────────
class TestCircuit:
    def test_open_after_threshold(self):
        g = SolverGuard(circuit_threshold=3)
        for _ in range(3):
            g.record_failure("http_error")
        assert g.circuit_open
        assert g.snapshot()["solver_status"] == "circuit_open"
        assert g.snapshot()["circuit_opened_at"] is not None
        # OPEN 后首次检查即放行一个 half-open 探测（后续由真实 acquire 触发），随后间隔内禁止
        assert g.allow_solve() is True
        assert g.allow_solve() is False

    def test_not_open_below_threshold(self):
        g = SolverGuard(circuit_threshold=5)
        for _ in range(4):
            g.record_failure("timeout")
        assert not g.circuit_open
        assert g.allow_solve()

    def test_allow_solve_when_closed(self):
        g = SolverGuard()
        assert g.allow_solve()

    def test_half_open_probe_release(self):
        g = SolverGuard(circuit_threshold=2, probe_interval=0.05)
        g.record_failure("timeout")
        g.record_failure("timeout")
        assert g.circuit_open
        # half-open：每 probe_interval 放行一个探测
        assert g.allow_solve() is True
        assert g.allow_solve() is False  # 间隔内不再放行
        time.sleep(0.06)
        assert g.allow_solve() is True

    def test_recover_on_probe_success(self):
        g = SolverGuard(circuit_threshold=2, probe_interval=0.05)
        g.record_failure("timeout")
        g.record_failure("timeout")
        assert g.circuit_open
        g.record_success(1.0)  # 探测成功 → 恢复 CLOSED
        assert not g.circuit_open
        assert g.snapshot()["solver_status"] == "ok"
        assert g.snapshot()["circuit_opened_at"] is None
        assert g.allow_solve()

    def test_consecutive_failures_reset_on_success(self):
        g = SolverGuard()
        g.record_failure("timeout")
        g.record_success(1.0)
        g.record_failure("timeout")
        s = g.snapshot()
        assert s["consecutive_failures"] == 1
        assert s["last_failure_at"] is not None
        assert s["solver_status"] == "degraded"  # 有失败但未熔断

    def test_success_clears_circuit_and_counter(self):
        g = SolverGuard(circuit_threshold=2)
        g.record_failure("timeout")
        g.record_failure("timeout")
        g.record_success(1.0)
        assert g.consecutive_failures == 0
        assert g.snapshot()["solve_success_total"] == 1
        assert g.snapshot()["solve_failure_total"] == 2
