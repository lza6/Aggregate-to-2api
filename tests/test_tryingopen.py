"""tryingopen ChatProvider 定向测试。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from api.providers import tryingopen
from api.providers.tryingopen import TryingopenChatProvider


class FakeResponse:
    def __init__(self, lines: list[str | bytes], status_code: int = 200, body: str = "") -> None:
        self.status_code = status_code
        self._lines = lines
        self._body = body

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self):
        return self._body.encode()


async def collect(provider: TryingopenChatProvider, *args, **kwargs) -> list[dict]:
    return [event async for event in provider.chat_stream(*args, **kwargs)]


def sse(*events: dict) -> FakeResponse:
    lines = [f"data: {json.dumps(event, ensure_ascii=False)}".encode() for event in events]
    lines.append(b"data: [DONE]")
    return FakeResponse(lines)


# 生产里普通对话默认走真流式增量（_request_stream_events）；以下两个 case 测的是聚合
# 路径 _parse_response / _request_once，故显式传一个非空 tools 强制 streaming=False 走聚合。
_TEST_TOOLS = [
    {
        "type": "function",
        "function": {"name": "lookup", "parameters": {"type": "object"}},
    }
]


@pytest.mark.asyncio
async def test_chat_stream_parses_sse_and_usage(monkeypatch):
    provider = TryingopenChatProvider()
    response = sse(
        {"type": "start", "messageMetadata": {"modelName": "Qwen"}},
        {"type": "reasoning-start", "id": "r1"},
        {"type": "reasoning-delta", "id": "r1", "delta": "先想"},
        {"type": "reasoning-end", "id": "r1"},
        {"type": "text-start", "id": "t1"},
        {"type": "text-delta", "id": "t1", "delta": "你好"},
        {"type": "text-delta", "id": "t1", "delta": "！"},
        {"type": "text-end", "id": "t1"},
        {
            "type": "finish",
            "finishReason": "stop",
            "messageMetadata": {
                "inputTokens": 11,
                "outputTokens": 7,
                "totalTokens": 18,
                "reasoningTokens": 2,
            },
        },
    )
    monkeypatch.setattr(
        provider,
        "_request_once",
        lambda payload, proxy: provider._parse_response(response),
    )

    events = await collect(
        provider, "tryingopen/qwen/qwen3.8-27b", [{"role": "user", "content": "hi"}], tools=_TEST_TOOLS
    )

    assert [(event["type"], event.get("text"), event.get("finish_reason")) for event in events] == [
        ("reasoning", "先想", None),
        ("text", "你好！", None),
        ("usage", None, None),
        ("finish", None, "stop"),
    ]
    assert events[2]["usage"] == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
        "reasoning_tokens": 2,
    }


def test_convert_messages_folds_system_images_and_stable_ids():
    provider = TryingopenChatProvider()
    messages = [
        {"role": "system", "content": "遵守规则"},
        {
            "id": "fixed-user",
            "role": "user",
            "content": [
                {"type": "text", "text": "看图"},
                {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}},
            ],
        },
        {
            "role": "assistant",
            "content": "已处理",
            "tool_calls": [
                {"id": "call-1", "function": {"name": "lookup", "arguments": {"q": "x"}}},
            ],
        },
    ]

    first = provider._convert_messages(messages)
    second = provider._convert_messages(messages)

    assert first[0]["role"] == "user"
    assert first[0]["parts"][0]["text"] == "[SYSTEM INSTRUCTIONS]\n遵守规则\n[/SYSTEM INSTRUCTIONS]"
    assert first[0]["parts"][2] == {
        "type": "file",
        "mediaType": "image/png",
        "url": "https://example.test/a.png",
    }
    assert first[1]["parts"][-1]["text"] == '[called lookup({"q":"x"});]'
    assert first[0]["id"] == second[0]["id"] == "fixed-user"
    assert first[1]["id"].startswith("msg-")
    assert second[1]["id"].startswith("msg-")


@pytest.mark.asyncio
async def test_tool_call_emulation_and_plain_text(monkeypatch):
    provider = TryingopenChatProvider()
    tools = [
        {
            "type": "function",
            "function": {"name": "lookup", "parameters": {"type": "object"}},
        }
    ]
    tool_response = tryingopen._AttemptResult(text='前置说明 {"tool_call":{"name":"lookup","arguments":{"q":"x"}}}')
    monkeypatch.setattr(provider, "_request_once", lambda payload, proxy: tool_response)
    tool_events = await collect(
        provider, "tryingopen/qwen/qwen3.8-27b", [{"role": "user", "content": "查"}], tools=tools
    )
    assert [event["type"] for event in tool_events] == ["text", "tool_call", "finish"]
    assert tool_events[0]["text"] == "前置说明"
    assert tool_events[1]["name"] == "lookup"
    assert json.loads(tool_events[1]["arguments"]) == {"q": "x"}
    assert tool_events[-1]["finish_reason"] == "tool_calls"

    plain_response = tryingopen._AttemptResult(text="普通回答")
    monkeypatch.setattr(provider, "_request_once", lambda payload, proxy: plain_response)
    plain_events = await collect(
        provider, "tryingopen/qwen/qwen3.8-27b", [{"role": "user", "content": "答"}], tools=tools
    )
    assert [event["type"] for event in plain_events] == ["text", "finish"]
    assert plain_events[-1]["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_refresh_models_updates_registry(monkeypatch):
    provider = TryingopenChatProvider()
    registry = SimpleNamespace(_chat_models={})
    provider._registry_ref = registry
    catalog = [
        {
            "id": "z-ai/glm-5.3-flash",
            "name": "GLM Flash",
            "context": "128k",
            "supportsTools": True,
            "supportsImages": True,
            "pricePerMTok": 0.2,
            "messageLimit": 20,
        },
        {"id": "qwen/qwen3.8-27b", "name": "Qwen", "context": "1m"},
    ]
    monkeypatch.setattr(provider, "_fetch_catalog", lambda: catalog)

    count = await provider.refresh_models()

    assert count >= 13
    assert "tryingopen/z-ai/glm-5.3-flash" in provider.models
    assert "tryingopen/qwen/qwen3.8-27b" in provider.models
    flash = provider.models["tryingopen/z-ai/glm-5.3-flash"]
    assert {"chat", "chat_tools", "chat_vision"} <= set(flash.capabilities)
    assert flash.meta["context_window"] == 128 * 1024
    assert flash.meta["messageLimit"] == 20
    assert registry._chat_models == provider.models
    assert provider.catalog_stats()["source"] == "live"


@pytest.mark.asyncio
async def test_429_marks_proxy_retries_and_succeeds(monkeypatch):
    provider = TryingopenChatProvider()
    calls = 0
    failures: list[tuple[str, bool]] = []
    successes: list[str] = []

    class FakePool:
        async def acquire(self, **kwargs):
            return "http://free-1"

        async def mark_failure(self, url, rate_limited=True):
            failures.append((url, rate_limited))

        async def mark_success(self, url):
            successes.append(url)

    async def request(payload, proxy):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise tryingopen._TryingopenRateLimited("You've used all 20 free messages")
        return tryingopen._AttemptResult(text="成功")

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(tryingopen, "proxy_pool", FakePool())
    monkeypatch.setattr(tryingopen.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(provider, "_request_once", request)
    monkeypatch.setenv("IF_TRYINGOPEN_MAX_ATTEMPTS", "2")

    events = await collect(
        provider, "tryingopen/qwen/qwen3.8-27b", [{"role": "user", "content": "hi"}], tools=_TEST_TOOLS
    )

    assert calls == 2
    assert failures == [("http://free-1", True)]
    assert successes == ["http://free-1"]
    assert events[-1] == {"type": "finish", "finish_reason": "stop"}


def test_fallback_catalog_has_required_models_and_kimi_meta():
    provider = TryingopenChatProvider()
    assert len(provider.models) >= 13
    kimi = provider.models["tryingopen/moonshotai/kimi-k3"]
    assert kimi.meta["messageLimit"] == 5
    assert kimi.meta["cheaperFallbackId"] == "minimax/minimax-m3"


def test_parse_fenced_tool_call_variants():
    calls = tryingopen._parse_plaintext_tool_calls('```json\n{"tool":{"name":"lookup","parameters":{"q":"x"}}}\n```')
    assert calls == [{"name": "lookup", "arguments": '{"q":"x"}'}]
