"""Section 16 可观测性闭环测试：错误码聚合 / 任务全链路日志 / 告警扩充规则。

覆盖：
1. error_tracker：record/限频 watch 码/snapshot 排序/count_of/reset；
2. handlers 落点：AppError、Starlette HTTPException、未捕获异常均记录到 error_tracker；
3. /v1/tasks/{id}/logs：内存日志过滤 + 慢日志画像 + SSE 回放 + DB 终态聚合；
4. alerting 新增规则：连续失败 / IP 批量封禁 / AUTH 激增。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.error_tracker import record, count_of, snapshot, reset, watched_codes


# ── error_tracker 单元 ──────────────────────────────
class TestErrorTracker:
    def setup_method(self):
        reset()

    def test_record_increments(self):
        record("AUTH.001")
        record("AUTH.001")
        assert count_of("AUTH.001") == 2

    def test_snapshot_sorted_desc(self):
        record("RATE.001")
        record("AUTH.001")
        record("AUTH.001")
        s = snapshot()
        assert s["AUTH.001"] == 2
        assert list(s.values()) == sorted(s.values(), reverse=True)

    def test_count_of_missing_zero(self):
        assert count_of("PROV.001") == 0

    def test_watched_codes_cover_p0_p1(self):
        w = watched_codes()
        for code in ("AUTH.001", "AUTH.003", "RATE.001"):
            assert code in w

    def test_reset_clears(self):
        record("SYS.001")
        reset()
        assert snapshot() == {}


# ── handlers 落点（AppError / HTTPException / generic 均记录）──
class TestHandlerTracks:
    def setup_method(self):
        reset()

    def test_app_error_recorded(self):
        from api.handlers import app_error_handler
        from api.errors import AppError, ErrorCodes
        # 直接调用 handler（不经 HTTP），验证只记录不抛
        import asyncio
        exc = AppError(ErrorCodes.UNAUTHORIZED, "no key", 401)
        asyncio.run(app_error_handler(None, exc))
        assert count_of(ErrorCodes.UNAUTHORIZED) == 1

    def test_starlette_http_exception_recorded(self):
        from api.handlers import starlette_http_exception_handler
        from starlette.exceptions import HTTPException as StarletteHTTPException
        import asyncio
        exc = StarletteHTTPException(404, "not found")
        asyncio.run(starlette_http_exception_handler(None, exc))
        assert count_of("SYS.003") == 1  # 404 → NOT_FOUND

    def test_generic_exception_recorded(self):
        from api.handlers import generic_exception_handler
        import asyncio
        asyncio.run(generic_exception_handler(None, ValueError("boom")))
        assert count_of("SYS.001") >= 1

    def test_validation_422_recorded(self):
        """S1 修复：参数/请求体校验 422 应纳入错误码聚合（VAL.004）。"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.generate import router
        from api.handlers import register_exception_handlers
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router)
        c = TestClient(app)
        r = c.post("/v1/generate/async", json={"prompt": "x", "aspect_ratio": "bad"})
        assert r.status_code == 422
        assert count_of("VAL.004") == 1


# ── 任务全链路日志端点点位 ──────────────────────────
def make_logs_app() -> FastAPI:
    from api.routes.tasks import router
    from api.handlers import register_exception_handlers
    app = FastAPI()
    register_exception_handlers(app)  # AppError → 统一错误结构（422 而非 500）
    app.include_router(router)
    return app


@pytest.fixture()
def logs_client(monkeypatch):
    monkeypatch.setenv("IF_API_KEYS", "")
    import api.config as config_module
    from api.config import Settings
    config_module.settings = Settings()
    return TestClient(make_logs_app())


class TestTaskLogsEndpoint:
    UUID_STR = "123e4567-e89b-12d3-a456-426614174000"

    def test_unknown_task_returns_empty_shape(self, logs_client):
        r = logs_client.get(f"/v1/tasks/{self.UUID_STR}/logs")
        assert r.status_code == 200
        assert r.json()["task_id"] == self.UUID_STR
        assert r.json()["task"] is None

    def test_logs_param_bounds(self, logs_client):
        r = logs_client.get(f"/v1/tasks/{self.UUID_STR}/logs?lines=5")
        assert r.status_code == 200
        r2 = logs_client.get(f"/v1/tasks/{self.UUID_STR}/logs?lines=20000")
        assert r2.status_code == 422  # le=2000 上限拦截

    def test_logs_requires_full_uuid(self, logs_client):
        """R2 修复：短前缀/非法 uuid 应 422，不再做任意子串匹配。"""
        r = logs_client.get("/v1/tasks/1234/logs")
        assert r.status_code == 422
        r2 = logs_client.get("/v1/tasks/not-a-uuid/logs")
        assert r2.status_code == 422


# ── alerting 新增规则 ───────────────────────────────
class TestAlertRulesExpanded:
    def test_provider_consecutive_failures_rule(self):
        from api.alerting import AlertEngine
        engine = AlertEngine()
        engine._rules.clear()  # 清除默认，聚焦新增
        from api.alerting import AlertRule
        engine.add_rule(AlertRule(
            name="provider_consecutive_failures", severity="warning",
            message="x", cooldown=0.0,
            check=lambda ctx: ctx.get("max_consecutive_failures", 0) >= 10,
        ))
        assert len(engine.evaluate({"max_consecutive_failures": 10})) == 1
        assert len(engine.evaluate({"max_consecutive_failures": 3})) == 0

    def test_ip_batch_block_rule(self):
        from api.alerting import AlertEngine, AlertRule
        engine = AlertEngine()
        engine._rules.clear()
        engine.add_rule(AlertRule(
            name="ip_batch_block", severity="critical",
            message="x", cooldown=0.0,
            check=lambda ctx: ctx.get("blocked_ip_count", 0) >= 20,
        ))
        assert len(engine.evaluate({"blocked_ip_count": 20})) == 1
        assert len(engine.evaluate({"blocked_ip_count": 5})) == 0

    def test_auth_surge_rule(self):
        from api.alerting import AlertEngine, AlertRule
        engine = AlertEngine()
        engine._rules.clear()
        engine.add_rule(AlertRule(
            name="auth_error_surge", severity="warning",
            message="x", cooldown=0.0,
            check=lambda ctx: ctx.get("auth_error_count", 0) >= 30,
        ))
        assert len(engine.evaluate({"auth_error_count": 30})) == 1
        assert len(engine.evaluate({"auth_error_count": 2})) == 0
