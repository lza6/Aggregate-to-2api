"""P3-D3: 成本预算燃烧预测测试。

覆盖：
- predict_budget_burn 核心数学逻辑（日均/预测日期/已超预算/无历史/预算关闭）
- chat_usage.cost_daily 日级聚合
- /v1/cost-forecast 端点（含管理 Key 鉴权 + 预算=0 降级）
"""

from __future__ import annotations

import time
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api import chat_usage
from api.cost_forecast import predict_budget_burn
from api.errors import AppError
from api.handlers import app_error_handler
from api.routes import admin

MODEL = "tryingopen/qwen/qwen3.8-27b"


async def _request(application: FastAPI, method: str, url: str, **kwargs):
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        return await client.request(method, url, **kwargs)


@pytest.fixture
def cost_app(monkeypatch):
    """挂载 admin 路由的 FastAPI 应用（/v1/cost-forecast 端点）。"""
    application = FastAPI()
    application.add_exception_handler(AppError, app_error_handler)
    application.include_router(admin.router)
    return application


# ── predict_budget_burn 纯数学逻辑 ────────────────────────────────


def test_predict_budget_burn_disabled_when_budget_zero():
    """预算=0 → disabled=True，projected_exceed_date=None。"""
    result = predict_budget_burn(
        daily_costs=[{"day": "2026-08-01", "cost_usd": 1.0, "calls": 1}],
        budget_usd=0.0,
    )
    assert result["disabled"] is True
    assert result["projected_exceed_date"] is None
    assert result["days_remaining"] is None
    assert result["budget_usd"] == 0.0
    assert result["daily_avg_30d"] > 0  # 仍回传日均参考


def test_predict_budget_burn_no_history():
    """无消耗历史 → daily_avg=0，无法预测。"""
    result = predict_budget_burn(daily_costs=[], budget_usd=10.0)
    assert result["disabled"] is False
    assert result["daily_avg_30d"] == 0.0
    assert result["projected_exceed_date"] is None
    assert result["days_remaining"] is None
    assert "无法预测" in result["note"]


def test_predict_budget_burn_already_over():
    """近 30 天累计已超预算 → days_remaining=0，projected_exceed_date=今天。"""
    today = date.today()
    daily_costs = [
        {"day": (today - timedelta(days=i)).strftime("%Y-%m-%d"), "cost_usd": 5.0, "calls": 1}
        for i in range(30)
    ]
    result = predict_budget_burn(daily_costs, budget_usd=10.0)
    assert result["disabled"] is False
    assert result["days_remaining"] == 0.0
    assert result["projected_exceed_date"] == today.strftime("%Y-%m-%d")
    assert result["current_spent_30d"] == 150.0  # 30 × 5


def test_predict_budget_burn_forecast_future():
    """按当前速率预测未来超预算日期。

    构造：近 30 天每天消耗 1 USD → 累计 30，日均 1.0；预算 100 → 剩余 70，
    days_remaining=70.0，projected_exceed_date = today + 70 天。
    """
    today = date.today()
    daily_costs = [
        {"day": (today - timedelta(days=i)).strftime("%Y-%m-%d"), "cost_usd": 1.0, "calls": 1}
        for i in range(30)
    ]
    result = predict_budget_burn(daily_costs, budget_usd=100.0)
    assert result["disabled"] is False
    assert result["daily_avg_30d"] == 1.0
    assert result["current_spent_30d"] == 30.0
    assert result["days_remaining"] == 70.0
    expected_date = (today + timedelta(days=70)).strftime("%Y-%m-%d")
    assert result["projected_exceed_date"] == expected_date


def test_predict_budget_burn_uses_30_day_denominator():
    """日均 = 累计 / 30（缺失天视为 0），而非累计 / 实际有数据天数。

    构造：仅 1 天有消耗 30 USD → 累计 30，日均 = 30/30 = 1.0（非 30/1=30）。
    """
    today = date.today()
    daily_costs = [
        {"day": today.strftime("%Y-%m-%d"), "cost_usd": 30.0, "calls": 1},
    ]
    result = predict_budget_burn(daily_costs, budget_usd=100.0)
    assert result["daily_avg_30d"] == 1.0  # 30/30，非 30
    assert result["current_spent_30d"] == 30.0
    # 剩余 70 / 日均 1 = 70 天
    assert result["days_remaining"] == 70.0


# ── chat_usage.cost_daily 日级聚合 ────────────────────────────────


@pytest.mark.asyncio
async def test_cost_daily_aggregation(tmp_db):
    """cost_daily 按天聚合 cost_usd + calls。"""
    tracker = chat_usage.ChatUsageTracker(db=tmp_db)
    # 同一天两条记录
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
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.7,
        duration_ms=1,
        success=True,
    )
    await tmp_db._ensure_flushed()
    rows = await tracker.cost_daily(30)
    assert rows
    today_label = time.strftime("%Y-%m-%d", time.localtime())
    today_row = next((r for r in rows if r["day"] == today_label), None)
    assert today_row is not None
    assert today_row["cost_usd"] == 1.0  # 0.3 + 0.7
    assert today_row["calls"] == 2


@pytest.mark.asyncio
async def test_cost_daily_empty(tmp_db):
    """无数据时 cost_daily 返回空列表。"""
    tracker = chat_usage.ChatUsageTracker(db=tmp_db)
    await tmp_db._ensure_flushed()
    rows = await tracker.cost_daily(30)
    assert rows == []


# ── /v1/cost-forecast 端点 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_v1_cost_forecast_disabled(cost_app, tmp_db, monkeypatch):
    """预算=0 → disabled=True，端点返回 200 + 降级字段。"""
    monkeypatch.setattr(chat_usage.chat_usage_tracker, "_db", tmp_db)
    from api import config

    monkeypatch.setattr(config, "IF_COST_BUDGET_USD", 0.0)

    # 开放管理 Key 模式（无 Key 也能过 check_admin_key）
    monkeypatch.setattr(config.settings, "if_admin_key_open", True)

    resp = await _request(cost_app, "GET", "/v1/cost-forecast")
    assert resp.status_code == 200
    body = resp.json()
    assert body["disabled"] is True
    assert body["projected_exceed_date"] is None
    assert body["days_remaining"] is None
    assert body["budget_usd"] == 0.0
    assert "daily_avg_30d" in body
    assert "current_spent_30d" in body
    assert "note" in body


@pytest.mark.asyncio
async def test_v1_cost_forecast_with_budget(cost_app, tmp_db, monkeypatch):
    """预算>0 + 有消耗历史 → 返回预测日期与剩余天数。"""
    monkeypatch.setattr(chat_usage.chat_usage_tracker, "_db", tmp_db)
    from api import config

    monkeypatch.setattr(config, "IF_COST_BUDGET_USD", 100.0)
    monkeypatch.setattr(config.settings, "if_admin_key_open", True)

    tracker = chat_usage.ChatUsageTracker(db=tmp_db)
    # 写一条 1 USD 消耗 → 日均 = 1/30，预算 100，剩余 99.967
    await tracker.record(
        provider="tryingopen",
        model=MODEL,
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=1.0,
        duration_ms=1,
        success=True,
    )
    await tmp_db._ensure_flushed()

    resp = await _request(cost_app, "GET", "/v1/cost-forecast")
    assert resp.status_code == 200
    body = resp.json()
    assert body["disabled"] is False
    assert body["budget_usd"] == 100.0
    assert body["current_spent_30d"] == 1.0
    # 日均 = 1/30 ≈ 0.0333
    assert abs(body["daily_avg_30d"] - 1.0 / 30.0) < 1e-6
    assert body["projected_exceed_date"] is not None
    assert body["days_remaining"] is not None
    assert body["days_remaining"] > 0


@pytest.mark.asyncio
async def test_v1_cost_forecast_requires_admin_key(cost_app, tmp_db, monkeypatch):
    """未配置管理 Key + 未开启开放模式 → 401/403。"""
    monkeypatch.setattr(chat_usage.chat_usage_tracker, "_db", tmp_db)
    from api import config

    monkeypatch.setattr(config, "IF_COST_BUDGET_USD", 10.0)
    # 关闭开放模式 + 不配管理 Key → check_admin_key 拒绝
    monkeypatch.setattr(config.settings, "if_admin_key_open", False)
    monkeypatch.setattr(config.settings, "if_admin_keys", "")
    monkeypatch.setattr(config.settings, "if_api_keys", "")

    resp = await _request(cost_app, "GET", "/v1/cost-forecast")
    assert resp.status_code in (401, 403)
