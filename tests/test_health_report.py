"""P2-10: 健康自诊断报告测试。

覆盖：
- build_health_report 聚合：七个维度字段齐全（mock 各来源返回固定数据）
- 单源采集抛异常 → 该项降级 {"error": ...}，不整端点 500
- GET /v1/admin/health-report：开放模式放行 200 / 字段齐全
- ?format=md → text/markdown 可读输出
- 非开放模式（无管理 Key）→ 401/403
- format_health_report_md 对含 error 降级项也不抛异常

全部只读 mock，不触发真实付费上游。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.errors import AppError
from api.handlers import app_error_handler
from api.routes import admin


async def _request(application: FastAPI, method: str, url: str, **kwargs):
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        return await client.request(method, url, **kwargs)


@pytest.fixture
def health_app(monkeypatch):
    """挂载 admin 路由的 FastAPI 应用（/v1/admin/health-report 端点）。"""
    application = FastAPI()
    application.add_exception_handler(AppError, app_error_handler)
    application.include_router(admin.router)
    return application


# ── build_health_report 聚合 ────────────────────────────────────────


def _fixed_report() -> dict:
    return {
        "generated_at": "2026-01-01T00:00:00",
        "providers": {
            "count": 1,
            "nodes": {
                "imagefree": {
                    "success_count": 90,
                    "failure_count": 10,
                    "success_rate": 0.9,
                    "ewma_latency_ms": 120.0,
                    "circuit_state": "closed",
                    "consecutive_failures": 0,
                    "in_flight_requests": 3,
                }
            },
        },
        "account_pool": {
            "count": 1,
            "total_ok": 5,
            "by_provider": {"nanobanana": {"ok": 5, "dead": 1, "cooling": 0}},
        },
        "email_pool": {"total_registered": 12, "by_status": {"ok": 10, "error": 2}},
        "solver": {
            "status": "ok",
            "node_count": 2,
            "healthy_node_count": 2,
            "circuit_open": False,
            "window_success_rate": 0.98,
            "window_solve_count": 50,
            "consecutive_failures": 0,
            "solve_total": 100,
            "solve_success_total": 98,
            "rejected_total": 1,
        },
        "queue": {
            "queued": 42,
            "processing": 7,
            "queue_capacity": 2000,
            "workers": 10,
            "by_priority": {"admin": 0, "high": 5, "normal": 37},
        },
        "runtime": {
            "memory": {"available": True, "rss_mb": 123.4},
            "sse_active_connections": 3,
            "workers": 10,
            "uptime_seconds": 3600,
        },
        "cost": {
            "daily_avg_30d": 1.0,
            "projected_exceed_date": "2026-02-01",
            "days_remaining": 31.0,
            "budget_usd": 100.0,
            "current_spent_30d": 30.0,
            "disabled": False,
            "note": "mock",
        },
    }


@pytest.mark.asyncio
async def test_build_health_report_all_fields(monkeypatch):
    """七维字段齐全（各来源返回固定数据）。"""
    import api.health_report as hr

    fixed = _fixed_report()

    def _providers(registry):
        return fixed["providers"]

    async def _account_pool():
        return fixed["account_pool"]

    async def _email_pool():
        return fixed["email_pool"]

    def _solver(solver_guard):
        return fixed["solver"]

    def _queue(engine):
        return fixed["queue"]

    def _runtime(engine, hub):
        return fixed["runtime"]

    async def _cost():
        return fixed["cost"]

    monkeypatch.setattr(hr, "_collect_providers", _providers)
    monkeypatch.setattr(hr, "_collect_account_pool", _account_pool)
    monkeypatch.setattr(hr, "_collect_email_pool", _email_pool)
    monkeypatch.setattr(hr, "_collect_solver", _solver)
    monkeypatch.setattr(hr, "_collect_queue", _queue)
    monkeypatch.setattr(hr, "_collect_runtime", _runtime)
    monkeypatch.setattr(hr, "_collect_cost", _cost)

    report = await hr.build_health_report()
    assert set(report) >= {
        "generated_at",
        "providers",
        "account_pool",
        "email_pool",
        "solver",
        "queue",
        "runtime",
        "cost",
    }
    # 抽样断言关键嵌套字段
    node = report["providers"]["nodes"]["imagefree"]
    assert node["success_rate"] == 0.9
    assert node["ewma_latency_ms"] == 120.0
    assert report["account_pool"]["by_provider"]["nanobanana"]["dead"] == 1
    assert report["queue"]["by_priority"]["normal"] == 37
    assert report["runtime"]["sse_active_connections"] == 3
    assert report["cost"]["budget_usd"] == 100.0
    assert report["solver"]["status"] == "ok"


@pytest.mark.asyncio
async def test_build_health_report_single_source_error(monkeypatch):
    """单源采集抛异常 → 该项降级 {"error": ...}，其余维度照常，不整端点 500。"""
    import api.health_report as hr

    fixed = _fixed_report()

    def _boom_providers(registry):
        raise RuntimeError("providers snapshot unavailable")

    async def _account_pool():
        return fixed["account_pool"]

    async def _email_pool():
        raise OSError("email db locked")

    def _solver(solver_guard):
        return fixed["solver"]

    def _queue(engine):
        return fixed["queue"]

    def _runtime(engine, hub):
        return fixed["runtime"]

    async def _cost():
        return fixed["cost"]

    monkeypatch.setattr(hr, "_collect_providers", _boom_providers)
    monkeypatch.setattr(hr, "_collect_account_pool", _account_pool)
    monkeypatch.setattr(hr, "_collect_email_pool", _email_pool)
    monkeypatch.setattr(hr, "_collect_solver", _solver)
    monkeypatch.setattr(hr, "_collect_queue", _queue)
    monkeypatch.setattr(hr, "_collect_runtime", _runtime)
    monkeypatch.setattr(hr, "_collect_cost", _cost)

    report = await hr.build_health_report()
    # 失败项降级
    assert "error" in report["providers"]
    assert "error" in report["email_pool"]
    # 其余维度不受影响
    assert report["solver"]["status"] == "ok"
    assert report["queue"]["queued"] == 42
    assert report["runtime"]["workers"] == 10
    assert report["cost"]["budget_usd"] == 100.0


@pytest.mark.asyncio
async def test_format_health_report_md(monkeypatch):
    """Markdown 输出可读：含标题/维度/数值；对 error 降级项也不抛异常。"""
    import api.health_report as hr

    report = _fixed_report()
    report["email_pool"] = {"error": "OSError: email db locked"}
    md = hr.format_health_report_md(report)
    assert md.startswith("# 健康自诊断报告")
    for section in ("providers", "account_pool", "email_pool", "solver", "queue", "runtime", "cost"):
        assert section in md
    assert "imagefree" in md
    assert "success_rate" in md
    # error 降级项可读
    assert "OSError" in md


# ── /v1/admin/health-report 端点 ────────────────────────────────────


def _open_admin(monkeypatch):
    from api import config

    monkeypatch.setattr(config.settings, "if_admin_key_open", True)


def _lock_admin(monkeypatch):
    from api import config

    monkeypatch.setattr(config.settings, "if_admin_key_open", False)
    monkeypatch.setattr(config.settings, "if_admin_keys", "")
    monkeypatch.setattr(config.settings, "if_api_keys", "")


@pytest.mark.asyncio
async def test_endpoint_open_mode_ok(health_app, monkeypatch):
    """开放模式（IF_ADMIN_KEY_OPEN=1）→ 200 + 字段齐全。"""
    import api.health_report as hr

    _open_admin(monkeypatch)
    fixed = _fixed_report()
    async def _fixed_build() -> dict:
        return fixed
    monkeypatch.setattr(hr, "build_health_report", _fixed_build)

    resp = await _request(health_app, "GET", "/v1/admin/health-report")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("providers", "account_pool", "email_pool", "solver", "queue", "runtime", "cost", "generated_at"):
        assert key in body
    assert body["providers"]["nodes"]["imagefree"]["success_rate"] == 0.9


@pytest.mark.asyncio
async def test_endpoint_format_md(health_app, monkeypatch):
    """?format=md → text/markdown 可读输出。"""
    import api.health_report as hr

    _open_admin(monkeypatch)
    async def _fixed_build() -> dict:
        return _fixed_report()
    monkeypatch.setattr(hr, "build_health_report", _fixed_build)

    resp = await _request(health_app, "GET", "/v1/admin/health-report?format=md")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "# 健康自诊断报告" in resp.text
    assert "success_rate" in resp.text


@pytest.mark.asyncio
async def test_endpoint_requires_admin_key(health_app, monkeypatch):
    """非开放模式 + 未配置管理 Key → 401/403。"""
    _lock_admin(monkeypatch)
    resp = await _request(health_app, "GET", "/v1/admin/health-report")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_endpoint_error_item_still_200(health_app, monkeypatch):
    """单项采集失败 → 端点仍 200，失败项带 error 字段（不整端点 500）。"""
    import api.health_report as hr

    _open_admin(monkeypatch)
    fixed = _fixed_report()
    fixed["solver"] = {"error": "RuntimeError: solver down"}
    async def _fixed_build() -> dict:
        return fixed
    monkeypatch.setattr(hr, "build_health_report", _fixed_build)

    resp = await _request(health_app, "GET", "/v1/admin/health-report")
    assert resp.status_code == 200
    assert "error" in resp.json()["solver"]
