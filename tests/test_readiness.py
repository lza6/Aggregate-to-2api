"""M6-F1: 就绪/存活语义对齐测试。

区分 liveness（进程活）与 readiness（依赖 ok）：
- /v1/livez 恒 200，停 solver 不误杀
- /v1/readyz 任一依赖不 ok → 503，恢复后回 200

注意：不在模块顶部 import api.*，避免 collection 期触发 api 模块树加载、
破坏 conftest._app_instance 的 purge 机制（导致 account_pool 双版本分叉）。
"""
import pytest


@pytest.mark.integration
class TestReadinessLiveness:
    """livez/readyz 语义对齐（集成 fixture：mock cfsolver + app）。"""

    async def test_livez_always_ok(self, app_with_mocks):
        """livez 恒 200 + status=='ok'，不探外部依赖。"""
        r = await app_with_mocks.get("/v1/livez")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "timestamp" in body

    async def test_readyz_ok_when_healthy(self, app_with_mocks):
        """健康状态下 readyz 200 + status=='ready'。"""
        r = await app_with_mocks.get("/v1/readyz")
        assert r.status_code == 200, f"期望 200，实际 {r.status_code}: {r.text}"
        body = r.json()
        assert body["status"] == "ready"
        assert body["reasons"] == []

    async def test_healthz_still_ok_regression(self, app_with_mocks):
        """回归：/v1/healthz 仍 200（不破坏现状）。"""
        r = await app_with_mocks.get("/v1/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") in ("ok", "degraded")

    async def test_readyz_503_when_solver_down_and_livez_ok(
        self, app_with_mocks, monkeypatch
    ):
        """破坏 cf_solver 可达性 → readyz 503 reasons 含 cf_solver；livez 仍 200。

        验证「readiness 降级而 liveness 不误杀」核心契约。
        """
        from api.routes import health as health_routes

        async def _broken_probe(force: bool = False) -> bool:
            return False

        monkeypatch.setattr(health_routes, "_probe_cf_solver", _broken_probe)

        # readyz 应 503
        r = await app_with_mocks.get("/v1/readyz")
        assert r.status_code == 503, f"期望 503，实际 {r.status_code}: {r.text}"
        body = r.json()
        assert body["status"] == "not_ready"
        assert any("cf_solver" in reason for reason in body["reasons"])

        # livez 仍 200（不误杀）
        r2 = await app_with_mocks.get("/v1/livez")
        assert r2.status_code == 200
        assert r2.json()["status"] == "ok"

    async def test_readyz_503_when_solver_circuit_open(
        self, app_with_mocks, monkeypatch
    ):
        """solver_guard 熔断 → readyz 503 reasons 含 solver。"""
        from api.routes import health as health_routes

        def _circuit_snapshot():
            return {
                "solver_status": "circuit_open",
                "circuit_open": True,
                "solve_success_total": 0,
                "solve_failure_total": 3,
                "solve_avg_seconds": None,
                "window_success_rate": 0.0,
                "window_solve_count": 3,
                "consecutive_failures": 3,
                "last_failure_at": 1700000000,
                "rejected_total": 0,
            }

        monkeypatch.setattr(
            health_routes.solver_guard, "snapshot", _circuit_snapshot
        )

        r = await app_with_mocks.get("/v1/readyz")
        assert r.status_code == 503, f"期望 503，实际 {r.status_code}: {r.text}"
        body = r.json()
        assert body["status"] == "not_ready"
        assert any("solver" in reason for reason in body["reasons"])

    async def test_readyz_recovers(self, app_with_mocks, monkeypatch):
        """破坏后恢复 _probe_cf_solver → readyz 回 200。"""
        from api.routes import health as health_routes

        async def _broken_probe(force: bool = False) -> bool:
            return False

        async def _healthy_probe(force: bool = False) -> bool:
            return True

        # 先破坏
        monkeypatch.setattr(health_routes, "_probe_cf_solver", _broken_probe)
        r_down = await app_with_mocks.get("/v1/readyz")
        assert r_down.status_code == 503

        # 恢复
        monkeypatch.setattr(health_routes, "_probe_cf_solver", _healthy_probe)
        r_up = await app_with_mocks.get("/v1/readyz")
        assert r_up.status_code == 200, f"恢复后期望 200，实际 {r_up.status_code}"
        assert r_up.json()["status"] == "ready"
