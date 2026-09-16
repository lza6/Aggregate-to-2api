"""P2-9: 成本预测预警推送测试。

覆盖：
- 超阈值 → webhook 被调一次 + payload 字段（pct/预算/已耗/预测）
- 未超阈值 → 不调
- 幂等：同水位/小幅上涨（<5pp）第二次不调
- 水位上升 >=5pp → 再推
- 回落阈值以下 → 水位复位，下次重新越过再推
- IF_COST_ALERT_PCT=0 关闭 → 不调
- 未配置 webhook URL → 触发但不上链外发（仅记日志）

不触发真实付费上游：预测数据全部由 mock 提供。
"""

from __future__ import annotations

from typing import Any

import pytest

import api.alerting
import api.config as config
from api import cost_alert


class _SendCapture:
    """捕获 alerting._send_webhook 调用（entries/url）。async 使 `await` 成功（L7 水位后置语义）。"""

    def __init__(self) -> None:
        self.calls: list[tuple[list[Any], str]] = []

    async def __call__(self, entries: Any, url: str) -> Any:
        self.calls.append((entries, url))
        return None


def _forecast(spent: float, budget: float = 100.0, *, disabled: bool = False) -> dict:
    """构造 predict_budget_burn 形状的 mock 输出。"""
    return {
        "daily_avg_30d": round(spent / 30.0, 6) if spent else 0.0,
        "projected_exceed_date": "2099-01-01" if not disabled else None,
        "days_remaining": 10.0 if not disabled else None,
        "budget_usd": 0.0 if disabled else budget,
        "current_spent_30d": round(spent, 6),
        "disabled": disabled,
        "note": "mock",
    }


@pytest.fixture(autouse=True)
def _reset_state():
    """每个用例前复位进程级幂等水位（模块全局，须显式清）。"""
    cost_alert._reset_alert_state()
    yield
    cost_alert._reset_alert_state()


@pytest.fixture
def capture(monkeypatch):
    """注入 webhook 发送捕获 + 默认阈值 80 / 配好 URL。"""
    cap = _SendCapture()
    monkeypatch.setattr(cost_alert, "_collect_forecast", _forecast_spent(60.0))
    monkeypatch.setattr(api.alerting, "_send_webhook", cap)
    monkeypatch.setattr(config, "IF_COST_ALERT_PCT", 80.0)
    monkeypatch.setattr(config, "IF_ALERT_WEBHOOK_URL", "https://example.invalid/hook")
    return cap


def _forecast_spent(spent: float, budget: float = 100.0, *, disabled: bool = False) -> Any:
    async def _inner() -> dict:
        return _forecast(spent, budget, disabled=disabled)

    return _inner


@pytest.mark.asyncio
async def test_alert_sends_when_over_threshold(capture, monkeypatch):
    """超阈值（85% >= 80%）→ webhook 被调一次 + payload 字段齐全。"""
    monkeypatch.setattr(cost_alert, "_collect_forecast", _forecast_spent(85.0))
    payload = await cost_alert.run_cost_alert_once()

    assert payload is not None
    assert payload["burn_pct"] == 85.0
    assert payload["threshold_pct"] == 80.0
    assert payload["budget_usd"] == 100.0
    assert payload["spent_usd"] == 85.0
    assert payload["projected_exceed_date"] == "2099-01-01"
    assert payload["days_remaining"] == 10.0
    assert payload["name"] == "cost_alert_pct"
    # webhook 被调一次，携带含 pct 的 messages
    assert len(capture.calls) == 1
    entries, url = capture.calls[0]
    assert url == "https://example.invalid/hook"
    assert entries[0]["name"] == "cost_alert_pct"
    assert "85.0%" in entries[0]["message"]


@pytest.mark.asyncio
async def test_no_alert_below_threshold(capture):
    """未超阈值（50% < 80%）→ 不调 webhook。"""
    # capture fixture 默认 spent=60 -> pct=60 < 80
    payload = await cost_alert.run_cost_alert_once()
    assert payload is None
    assert capture.calls == []


@pytest.mark.asyncio
async def test_idempotent_same_water_level(capture, monkeypatch):
    """同水位 / 小幅上涨（<5pp）第二次不重复推。"""
    monkeypatch.setattr(cost_alert, "_collect_forecast", _forecast_spent(85.0))
    first = await cost_alert.run_cost_alert_once()
    assert first is not None

    # 同水位 → 不推
    assert await cost_alert.run_cost_alert_once() is None
    # 小幅上涨（85 -> 88，涨幅 3 < 5pp）→ 不推
    monkeypatch.setattr(cost_alert, "_collect_forecast", _forecast_spent(88.0))
    assert await cost_alert.run_cost_alert_once() is None

    assert len(capture.calls) == 1


@pytest.mark.asyncio
async def test_repush_after_water_rise_over_5pp(capture, monkeypatch):
    """水位上升 >=5pp 后再推一次。"""
    monkeypatch.setattr(cost_alert, "_collect_forecast", _forecast_spent(85.0))
    assert await cost_alert.run_cost_alert_once() is not None

    # 85 -> 92，涨幅 7 >= 5pp → 再推
    monkeypatch.setattr(cost_alert, "_collect_forecast", _forecast_spent(92.0))
    assert await cost_alert.run_cost_alert_once() is not None

    assert len(capture.calls) == 2


@pytest.mark.asyncio
async def test_reset_after_fall_below_threshold(capture, monkeypatch):
    """回落到阈值以下复位水位，下次重新越过阈值再推。"""
    monkeypatch.setattr(cost_alert, "_collect_forecast", _forecast_spent(85.0))
    assert await cost_alert.run_cost_alert_once() is not None

    # 回落（60 < 80）→ 不推 + 水位复位
    monkeypatch.setattr(cost_alert, "_collect_forecast", _forecast_spent(60.0))
    assert await cost_alert.run_cost_alert_once() is None

    # 重新越过（85）→ 再推（水位已复位，不因涨幅逻辑被抑制）
    monkeypatch.setattr(cost_alert, "_collect_forecast", _forecast_spent(85.0))
    assert await cost_alert.run_cost_alert_once() is not None

    assert len(capture.calls) == 2


@pytest.mark.asyncio
async def test_disabled_when_threshold_zero(capture, monkeypatch):
    """IF_COST_ALERT_PCT=0 → 关闭，即使超阈值也不调。"""
    monkeypatch.setattr(config, "IF_COST_ALERT_PCT", 0.0)
    monkeypatch.setattr(cost_alert, "_collect_forecast", _forecast_spent(95.0))
    assert await cost_alert.run_cost_alert_once() is None
    assert capture.calls == []


@pytest.mark.asyncio
async def test_no_webhook_when_url_missing(capture, monkeypatch):
    """超阈值但未配置 IF_ALERT_WEBHOOK_URL → 触发（返回 payload）但不上链外发。"""
    monkeypatch.setattr(cost_alert, "_collect_forecast", _forecast_spent(85.0))
    monkeypatch.setattr(config, "IF_ALERT_WEBHOOK_URL", "")
    payload = await cost_alert.run_cost_alert_once()
    assert payload is not None
    assert capture.calls == []


@pytest.mark.asyncio
async def test_disabled_forecast_never_triggers(capture, monkeypatch):
    """预算未配置（forecast.disabled=True）→ 不调。"""
    monkeypatch.setattr(
        cost_alert, "_collect_forecast", _forecast_spent(85.0, disabled=True)
    )
    assert await cost_alert.run_cost_alert_once() is None
    assert capture.calls == []


@pytest.mark.asyncio
async def test_alert_send_error_not_raised(capture, monkeypatch):
    """webhook 外发抛异常 → 不向上抛（不影响后台周期任务）。"""

    async def _boom(entries: Any, url: str) -> None:
        raise RuntimeError("network down")

    monkeypatch.setattr(cost_alert, "_collect_forecast", _forecast_spent(85.0))
    monkeypatch.setattr(api.alerting, "_send_webhook", _boom)
    payload = await cost_alert.run_cost_alert_once()
    assert payload is not None
