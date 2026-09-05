"""M6-F3 成本可视化与告警测试。

覆盖：
- chat_usage by_provider + day/month 列
- cost_monthly / cost_by_provider_model 月度聚合
- /v1/cost 端点（含 IF_USD_PER_CREDIT=0 默认与启用后图片成本估算）
- 成本告警规则（cost_over_budget / cost_burn_rate_warning）
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api import chat_usage
from api.alerting import AlertEngine
from api.errors import AppError
from api.handlers import app_error_handler
from api.routes import admin

MODEL = "tryingopen/qwen/qwen3.8-27b"


async def _request(application: FastAPI, method: str, url: str, **kwargs):
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        return await client.request(method, url, **kwargs)


@pytest.fixture
def cost_app(monkeypatch):
    """挂载 admin 路由的 FastAPI 应用（/v1/cost 端点）。"""
    application = FastAPI()
    application.add_exception_handler(AppError, app_error_handler)
    application.include_router(admin.router)
    return application


# ── chat_usage by_provider + day/month ───────────────────────────


@pytest.mark.asyncio
async def test_chat_usage_has_by_provider(tmp_db):
    """stats() 返回 by_provider 字段，按 provider 聚合 cost/calls/tokens。"""
    tracker = chat_usage.ChatUsageTracker(db=tmp_db)
    await tracker.record(
        provider="tryingopen",
        model=MODEL,
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.5,
        duration_ms=1,
        success=True,
    )
    await tracker.record(
        provider="nanobanana",
        model="nano-banana-pro",
        prompt_tokens=20,
        completion_tokens=10,
        cost_usd=0.2,
        duration_ms=1,
        success=True,
    )
    await tmp_db._ensure_flushed()
    stats = await tracker.stats("24h")
    assert "by_provider" in stats
    provs = {p["provider"]: p for p in stats["by_provider"]}
    assert "tryingopen" in provs
    assert "nanobanana" in provs
    assert provs["tryingopen"]["cost_usd"] == 0.5
    assert provs["nanobanana"]["cost_usd"] == 0.2
    assert provs["tryingopen"]["calls"] == 1


@pytest.mark.asyncio
async def test_chat_usage_by_model_has_provider(tmp_db):
    """by_model 每项含 provider 字段（M6-F3）。"""
    tracker = chat_usage.ChatUsageTracker(db=tmp_db)
    await tracker.record(
        provider="tryingopen",
        model=MODEL,
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.1,
        duration_ms=1,
        success=True,
    )
    await tmp_db._ensure_flushed()
    stats = await tracker.stats("24h")
    assert stats["by_model"]
    assert stats["by_model"][0]["provider"] == "tryingopen"


@pytest.mark.asyncio
async def test_chat_usage_records_day_month(tmp_db):
    """record 写入 day/month 列，值符合 YYYY-MM-DD / YYYY-MM 格式。"""
    import datetime

    tracker = chat_usage.ChatUsageTracker(db=tmp_db)
    await tracker.record(
        provider="tryingopen",
        model=MODEL,
        prompt_tokens=1,
        completion_tokens=1,
        cost_usd=0.0,
        duration_ms=1,
        success=True,
    )
    await tmp_db._ensure_flushed()
    row = await tracker._query_one(
        "SELECT day, month FROM chat_usage ORDER BY id DESC LIMIT 1",
        (),
    )
    assert row is not None
    day, month = row[0], row[1]
    assert day and len(day) == 10  # YYYY-MM-DD
    assert month and len(month) == 7  # YYYY-MM
    now = datetime.datetime.now()
    assert month == now.strftime("%Y-%m")


# ── cost_monthly / cost_by_provider_model ────────────────────────


@pytest.mark.asyncio
async def test_cost_monthly_aggregation(tmp_db):
    """cost_monthly 按月聚合 cost_usd + calls。"""
    tracker = chat_usage.ChatUsageTracker(db=tmp_db)
    await tracker.record(
        provider="tryingopen",
        model=MODEL,
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.3,
        duration_ms=1,
        success=True,
    )
    await tracker.record(
        provider="tryingopen",
        model=MODEL,
        prompt_tokens=20,
        completion_tokens=10,
        cost_usd=0.7,
        duration_ms=1,
        success=True,
    )
    await tmp_db._ensure_flushed()
    rows = await tracker.cost_monthly(12)
    assert rows
    current = rows[-1]
    assert current["month"] == time.strftime("%Y-%m", time.localtime()) or len(current["month"]) == 7
    assert current["cost_usd"] == 1.0
    assert current["calls"] == 2


@pytest.mark.asyncio
async def test_cost_by_provider_model(tmp_db):
    """cost_by_provider_model 按 provider+model 聚合。"""
    tracker = chat_usage.ChatUsageTracker(db=tmp_db)
    await tracker.record(
        provider="tryingopen",
        model=MODEL,
        prompt_tokens=5,
        completion_tokens=5,
        cost_usd=0.4,
        duration_ms=1,
        success=True,
    )
    await tracker.record(
        provider="nanobanana",
        model="nano-banana-pro",
        prompt_tokens=5,
        completion_tokens=5,
        cost_usd=0.6,
        duration_ms=1,
        success=True,
    )
    await tmp_db._ensure_flushed()
    rows = await tracker.cost_by_provider_model(12)
    provs = {(r["provider"], r["model"]): r for r in rows}
    assert ("tryingopen", MODEL) in provs
    assert ("nanobanana", "nano-banana-pro") in provs
    assert provs[("tryingopen", MODEL)]["cost_usd"] == 0.4
    assert provs[("nanobanana", "nano-banana-pro")]["cost_usd"] == 0.6


# ── /v1/cost 端点 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_v1_cost_endpoint(cost_app, tmp_db, monkeypatch):
    """GET /v1/cost 返回 200 + 完整字段。"""
    # 注入 tmp_db 到 chat_usage_tracker，并清空 gallery_cache
    monkeypatch.setattr(chat_usage.chat_usage_tracker, "_db", tmp_db)
    from api.meta import gallery_cache

    await gallery_cache.invalidate("cost:summary")

    tracker = chat_usage.ChatUsageTracker(db=tmp_db)
    await tracker.record(
        provider="tryingopen",
        model=MODEL,
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.5,
        duration_ms=1,
        success=True,
    )
    await tmp_db._ensure_flushed()

    # account_pool.cost_summary 用 monkeypatch 返回 0（避免依赖真实号池）
    async def _fake_cost_summary(provider):
        return {
            "total_credits_used": 0,
            "total_images_used": 0,
            "total_credits_earned": 0,
            "accounts_with_usage": 0,
            "total_accounts": 0,
            "avg_cost_per_image": None,
        }

    from api import account_pool

    monkeypatch.setattr(account_pool.account_pool, "cost_summary", _fake_cost_summary)

    resp = await _request(cost_app, "GET", "/v1/cost")
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "month_to_date_usd",
        "today_usd",
        "budget_usd",
        "budget_remaining_pct",
        "over_budget",
        "burn_rate_warning",
        "monthly",
        "by_provider",
        "by_model",
        "image_cost_usd_mtd",
        "note",
    ):
        assert key in body, f"缺少字段 {key}"
    assert body["today_usd"] == 0.5
    assert body["budget_remaining_pct"] == 100  # budget=0 → 100
    assert body["over_budget"] is False
    assert body["burn_rate_warning"] is False
    assert isinstance(body["monthly"], list)
    assert isinstance(body["by_provider"], list)
    assert isinstance(body["by_model"], list)


@pytest.mark.asyncio
async def test_v1_cost_image_cost_usd(cost_app, tmp_db, monkeypatch):
    """IF_USD_PER_CREDIT=0.01 + account_pool credits_used_total=100 → image_cost_usd_mtd ≈ 1.0。"""
    monkeypatch.setattr(chat_usage.chat_usage_tracker, "_db", tmp_db)
    from api.meta import gallery_cache

    await gallery_cache.invalidate("cost:summary")

    # 配置 IF_USD_PER_CREDIT=0.01
    from api import config

    monkeypatch.setattr(config, "IF_USD_PER_CREDIT", 0.01)

    # account_pool.cost_summary 返回 credits_used_total=100
    async def _fake_cost_summary(provider):
        return {
            "total_credits_used": 100,
            "total_images_used": 10,
            "total_credits_earned": 0,
            "accounts_with_usage": 1,
            "total_accounts": 1,
            "avg_cost_per_image": 10,
        }

    from api import account_pool

    monkeypatch.setattr(account_pool.account_pool, "cost_summary", _fake_cost_summary)

    # 无 token 成本数据 → month_to_date = 0 + image 1.0
    resp = await _request(cost_app, "GET", "/v1/cost")
    assert resp.status_code == 200
    body = resp.json()
    assert abs(body["image_cost_usd_mtd"] - 1.0) < 1e-6  # 100 * 0.01
    assert abs(body["month_to_date_usd"] - 1.0) < 1e-6  # token_mtd(0) + image(1.0)
    # by_provider 含 nanobanana 行（图片成本挂这里）
    nb = [p for p in body["by_provider"] if p["provider"] == "nanobanana"]
    assert nb and abs(nb[0]["cost_usd"] - 1.0) < 1e-6
    assert nb[0]["credits_used"] == 100
    assert nb[0]["images"] == 10


# ── 成本告警规则 ─────────────────────────────────────────────────


def test_cost_over_budget_alert():
    """cost_over_budget：月成本>=预算 → 触发；预算=0 → 不触发。"""
    engine = AlertEngine()
    # 找到 cost_over_budget 规则
    rule = next((r for r in engine._rules if r.name == "cost_over_budget"), None)
    assert rule is not None
    assert rule.check({"month_to_date_usd": 10, "budget_usd": 5}) is True
    assert rule.check({"month_to_date_usd": 10, "budget_usd": 20}) is False
    assert rule.check({"month_to_date_usd": 10, "budget_usd": 0}) is False  # 预算 0 不告警
    assert rule.check({"month_to_date_usd": 0, "budget_usd": 5}) is False  # 月成本 0


def test_cost_burn_rate_alert():
    """cost_burn_rate_warning：消耗>=阈值% → 触发；阈值 80 → 80% 触发、70% 不触发。"""
    engine = AlertEngine()
    rule = next((r for r in engine._rules if r.name == "cost_burn_rate_warning"), None)
    assert rule is not None
    # 8/10 = 80% >= 80 → 触发
    assert rule.check({"month_to_date_usd": 8, "budget_usd": 10}) is True
    # 7/10 = 70% < 80 → 不触发
    assert rule.check({"month_to_date_usd": 7, "budget_usd": 10}) is False
    # 预算 0 → 不触发（除零保护）
    assert rule.check({"month_to_date_usd": 5, "budget_usd": 0}) is False


def test_cost_alerts_in_default_rules():
    """AlertEngine 默认规则集含 cost_over_budget + cost_burn_rate_warning。"""
    engine = AlertEngine()
    names = {r.name for r in engine._rules}
    assert "cost_over_budget" in names
    assert "cost_burn_rate_warning" in names
    # 验证严重级别
    over = next(r for r in engine._rules if r.name == "cost_over_budget")
    burn = next(r for r in engine._rules if r.name == "cost_burn_rate_warning")
    assert over.severity == "critical"
    assert burn.severity == "warning"


def test_cost_over_budget_evaluate_triggers():
    """完整 evaluate：超预算 ctx → 返回 critical 告警条目。"""
    engine = AlertEngine()
    # 清除冷却（直接重置 _last_triggered）
    for r in engine._rules:
        r._last_triggered = 0.0
    result = engine.evaluate({"month_to_date_usd": 100, "budget_usd": 50})
    triggered = {t["name"] for t in result}
    assert "cost_over_budget" in triggered
    # burn_rate_warning 也应触发（100/50=200% >= 80%）
    assert "cost_burn_rate_warning" in triggered
