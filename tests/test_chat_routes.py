from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.errors import AppError
from api.handlers import app_error_handler
from api.providers.base import CAP_CHAT, ChatProvider, ModelSpec
from api.providers.registry import registry
from api import chat_usage
from api.routes import chat


MODEL = "tryingopen/qwen/qwen3.8-27b"


class FakeChatProvider(ChatProvider):
    prefix = "tryingopen"
    models = {
        MODEL: ModelSpec(
            id=MODEL,
            provider="tryingopen",
            upstream_model="qwen/qwen3.8-27b",
            capabilities=(CAP_CHAT,),
        )
    }

    def __init__(self, events: list[dict] | None = None) -> None:
        super().__init__()
        self.events = events or [
            {"type": "text", "text": "hello"},
            {
                "type": "usage",
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
            },
            {"type": "finish", "finish_reason": "stop"},
        ]
        self.calls: list[dict] = []

    async def refresh_models(self) -> int:
        return len(self.models)

    def chat_stream(self, model: str, messages: list[dict], **kwargs):
        self.calls.append({"model": model, "messages": messages, "kwargs": kwargs})

        async def iterator():
            for event in self.events:
                yield event

        return iterator()


@pytest.fixture
def fake_provider(monkeypatch):
    provider = FakeChatProvider()
    monkeypatch.setattr(registry, "_booted", True)
    monkeypatch.setattr(chat, "providers_bootstrap", lambda: None)
    monkeypatch.setitem(registry.chat_providers, provider.prefix, provider)
    monkeypatch.setitem(registry._chat_models, MODEL, provider.models[MODEL])
    return provider


@pytest.fixture
def app(monkeypatch):
    application = FastAPI()
    application.add_exception_handler(AppError, app_error_handler)
    application.include_router(chat.router)
    monkeypatch.setattr(chat.chat_usage, "record", _noop_record)
    return application


async def _noop_record(**kwargs):
    return None


async def request(application: FastAPI, method: str, url: str, **kwargs):
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        return await client.request(method, url, **kwargs)


@pytest.mark.asyncio
async def test_openai_non_stream_response_and_usage_record(app, fake_provider, monkeypatch):
    records = []

    async def record(**kwargs):
        records.append(kwargs)

    monkeypatch.setattr(chat.chat_usage, "record", record)
    response = await request(
        app,
        "POST",
        "/v1/chat/completions",
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": "Hi"}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == MODEL
    assert body["choices"][0]["message"] == {
        "role": "assistant",
        "content": "hello",
    }
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["usage"] == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
    }
    assert records[0]["success"] is True
    assert records[0]["model"] == MODEL


@pytest.mark.asyncio
async def test_openai_stream_response_contains_chunks_and_done(app, fake_provider):
    fake_provider.events = [
        {"type": "text", "text": "hel"},
        {"type": "reasoning", "text": "think"},
        {
            "type": "tool_call",
            "id": "call_1",
            "name": "search",
            "arguments": '{"q":"x"}',
        },
        {
            "type": "usage",
            "usage": {
                "prompt_tokens": 4,
                "completion_tokens": 3,
                "total_tokens": 7,
                "reasoning_tokens": 1,
            },
        },
        {"type": "finish", "finish_reason": "tool_calls"},
    ]
    response = await request(
        app,
        "POST",
        "/v1/chat/completions",
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
            "stream_options": {"include_usage": True},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    assert payloads[0]["choices"][0]["delta"] == {"role": "assistant"}
    assert any(item["choices"][0]["delta"].get("content") == "hel" for item in payloads)
    assert any(item["choices"][0]["delta"].get("reasoning_content") == "think" for item in payloads)
    assert any(item["choices"][0]["delta"].get("tool_calls") for item in payloads)
    assert any(item.get("usage", {}).get("total_tokens") == 7 for item in payloads)
    assert response.text.rstrip().endswith("data: [DONE]")


@pytest.mark.asyncio
async def test_anthropic_non_stream_response(app, fake_provider):
    fake_provider.events = [
        {"type": "text", "text": "answer"},
        {"type": "reasoning", "text": "because"},
        {
            "type": "usage",
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        },
        {"type": "finish", "finish_reason": "stop"},
    ]
    response = await request(
        app,
        "POST",
        "/v1/messages",
        json={
            "model": MODEL,
            "system": "You are helpful.",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 100,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "message"
    assert body["role"] == "assistant"
    assert body["content"] == [
        {"type": "text", "text": "answer"},
        {"type": "thinking", "thinking": "because"},
    ]
    assert body["stop_reason"] == "end_turn"
    assert body["usage"] == {"input_tokens": 5, "output_tokens": 2}
    assert fake_provider.calls[-1]["messages"][0]["role"] == "system"


@pytest.mark.asyncio
async def test_unknown_model_is_404(app, fake_provider):
    response = await request(
        app,
        "POST",
        "/v1/chat/completions",
        json={"model": "tryingopen/no-such-model", "messages": []},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SYS.003"


@pytest.mark.asyncio
async def test_missing_provider_is_503(app, fake_provider, monkeypatch):
    monkeypatch.delitem(registry.chat_providers, "tryingopen")
    response = await request(
        app,
        "POST",
        "/v1/chat/completions",
        json={"model": MODEL, "messages": []},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROV.001"


@pytest.mark.asyncio
async def test_remaining_credits_uses_successful_calls_and_available_proxies(tmp_db, monkeypatch):
    tracker = chat_usage.ChatUsageTracker(db=tmp_db)
    await tracker.record(
        provider="tryingopen",
        model=MODEL,
        prompt_tokens=1,
        completion_tokens=2,
        reasoning_tokens=0,
        cost_usd=0.0,
        tool_calls_count=0,
        duration_ms=1,
        success=True,
        proxy_used=None,
        error=None,
    )
    await tracker.record(
        provider="tryingopen",
        model=MODEL,
        prompt_tokens=1,
        completion_tokens=2,
        reasoning_tokens=0,
        cost_usd=0.0,
        tool_calls_count=0,
        duration_ms=1,
        success=False,
        proxy_used=None,
        error="failed",
    )

    class Entry:
        def __init__(self, available: bool):
            self.is_available = available

        def available(self, now: float) -> bool:
            return self.is_available

    monkeypatch.setattr(
        chat_usage,
        "proxy_pool",
        SimpleNamespace(entries=[Entry(True), Entry(True), Entry(False)]),
    )
    monkeypatch.setenv("IF_TRYINGOPEN_HOURLY_PER_IP", "20")

    result = await tracker.remaining_credits()
    assert result["available_proxies"] == 2
    assert result["calls_per_proxy_per_hour"] == 20
    assert result["hourly_limit"] == 40
    assert result["used_last_hour"] == 1
    assert result["remaining"] == 39


@pytest.mark.asyncio
async def test_usage_stats_aggregates_cost_usd(tmp_db, monkeypatch):
    """v6.6.0: cost_usd 成为真实字段并聚合进 usage（免费为 0，付费渠道可填非零）。"""
    tracker = chat_usage.ChatUsageTracker(db=tmp_db)
    await tracker.record(
        provider="tryingopen",
        model=MODEL,
        prompt_tokens=100,
        completion_tokens=50,
        reasoning_tokens=10,
        cost_usd=0.5,
        tool_calls_count=0,
        duration_ms=1,
        success=True,
        proxy_used=None,
        error=None,
    )
    await tracker.record(
        provider="tryingopen",
        model=MODEL,
        prompt_tokens=50,
        completion_tokens=25,
        reasoning_tokens=5,
        cost_usd=0.0,
        tool_calls_count=0,
        duration_ms=1,
        success=True,
        proxy_used=None,
        error=None,
    )
    await tmp_db._ensure_flushed()
    stats = await tracker.stats("24h")
    assert stats["cost_usd"] == 0.5
    assert stats["today_cost_usd"] == 0.5
    assert stats["total_calls"] == 2
