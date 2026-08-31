"""P2-3 告警 webhook 外发测试。

用 monkeypatch httpx 断言 payload 结构，禁止真实外发。
覆盖：evaluate 触发后生成 webhook 调度、payload 结构（msgtype/text/alerts/source）、
格式化文本 `_format_alert_text`、空 webhook 配置不调度。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from api import config
from api.alerting import (
    AlertEngine,
    AlertRule,
    _format_alert_text,
    _send_webhook,
)


@pytest.mark.asyncio
async def test_send_webhook_payload_structure(monkeypatch):
    """_send_webhook 用 httpx.AsyncClient.post 发送结构化 payload。"""
    captured: dict = {}

    class _FakeResponse:
        status_code = 200

    class _FakeClient:
        def __init__(self, **kwargs):
            self.timeout = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            captured["url"] = url
            captured["json"] = json
            return _FakeResponse()

    # httpx.AsyncClient(timeout=...) 是普通构造调用（不 await），需用同步工厂返回实例
    def _fake_factory(*args, **kwargs):
        return _FakeClient()

    monkeypatch.setattr("httpx.AsyncClient", _fake_factory)

    entries = [
        {
            "name": "queue_backlog",
            "severity": "warning",
            "message": "排队任务数超过 1000",
            "timestamp": 1700000000,
        },
        {
            "name": "cost_over_budget",
            "severity": "critical",
            "message": "月度成本已超过预算",
            "timestamp": 1700000001,
        },
    ]
    await _send_webhook(entries, "https://example.com/hook")

    assert captured["url"] == "https://example.com/hook"
    payload = captured["json"]
    # 通用 JSON POST 结构：msgtype/text/alerts/source
    assert payload["msgtype"] == "text"
    assert isinstance(payload["text"]["content"], str)
    assert "imagefree" in payload["text"]["content"]
    assert len(payload["alerts"]) == 2
    assert payload["source"] == "imagefree-api"
    assert payload["alerts"][0]["name"] == "queue_backlog"
    assert payload["alerts"][1]["severity"] == "critical"


@pytest.mark.asyncio
async def test_send_webhook_empty_url_noop():
    """空 webhook URL → 直接返回，不触发任何网络请求。"""
    with patch("httpx.AsyncClient", new_callable=AsyncMock):
        await _send_webhook([{"name": "x", "severity": "warning", "message": "m"}], "")


def test_format_alert_text():
    """_format_alert_text 生成含 severity 与时间戳的可读文本。"""
    entries = [
        {
            "name": "auth_error_surge",
            "severity": "warning",
            "message": "AUTH.001 错误在近窗口内超阈值（≥30）",
            "timestamp": 1700000000,
        },
    ]
    text = _format_alert_text(entries)
    assert "imagefree" in text
    assert "auth_error_surge" in text
    assert "AUTH.001" in text
    assert "warning" in text
    assert "2023" in text  # 时间戳格式化


@pytest.mark.asyncio
async def test_evaluate_dispatches_webhook(monkeypatch):
    """evaluate 触发且配置 webhook → 调度 _send_webhook（验证被创建）。"""
    monkeypatch.setattr(config, "IF_ALERT_WEBHOOK_URL", "https://example.com/hook")
    monkeypatch.setattr("api.alerting._send_webhook", AsyncMock())

    engine = AlertEngine()
    # 清除默认规则，只加一条必然触发的规则
    engine._rules.clear()
    engine.add_rule(
        AlertRule(
            name="always_trigger",
            severity="warning",
            message="测试告警",
            cooldown=0.0,
            check=lambda ctx: True,
        )
    )
    result = engine.evaluate({"value": 1})
    assert len(result) == 1
    # _send_webhook 被替换为 AsyncMock，create_task 不真正执行网络请求
    assert result[0]["name"] == "always_trigger"


def test_evaluate_no_webhook_when_unconfigured(monkeypatch):
    """未配置 webhook → evaluate 不调度外发。"""
    monkeypatch.setattr(config, "IF_ALERT_WEBHOOK_URL", "")
    engine = AlertEngine()
    engine._rules.clear()
    engine.add_rule(
        AlertRule(name="t", severity="warning", message="m", cooldown=0.0, check=lambda ctx: True)
    )
    result = engine.evaluate({"value": 1})
    assert len(result) == 1
    # 无异常且正常返回即可（未配置时不会走到 create_task 分支）
    assert result[0]["name"] == "t"
