"""M5-E1 补测：chat 路由流式帧与边缘分支（Anthropic 流式 / usage 归一化 / 错误帧）。

覆盖 api/routes/chat.py 缺失分支（_openai_effort、_provider_kwargs、
_normalize_usage 兜底、_anthropic_content 解析失败、流式异常帧、
chat_auth_status 管理员取完整 key 等）。
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.errors import AppError
from api.handlers import app_error_handler
from api.providers.base import CAP_CHAT, ChatProvider, ModelSpec
from api.providers.registry import registry
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
            {"type": "usage", "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}},
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


# ── 纯函数分支 ──────────────────────────────────
def test_openai_effort_default():
    assert chat._openai_effort(None) == "balanced"


def test_openai_effort_known():
    assert chat._openai_effort("minimal") == "quick"
    assert chat._openai_effort("high") == "deep"
    assert chat._openai_effort("medium") == "balanced"


def test_openai_effort_unknown_falls_back():
    assert chat._openai_effort("bogus") == "balanced"


def test_provider_kwargs_strips_known_fields():
    """_provider_kwargs 用 model_dump，需 pydantic 模型。"""
    from api.routes.chat import ChatCompletionsRequest

    req = ChatCompletionsRequest(
        model="m",
        messages=[],
        stream=True,
        reasoning_effort="low",
        stream_options={"include_usage": True},
    )
    kw = chat._provider_kwargs(req)
    assert "model" not in kw
    assert "messages" not in kw
    assert "stream" not in kw
    assert "reasoning_effort" not in kw
    assert "stream_options" not in kw
    assert kw["effort"] == "quick"  # low → quick


def test_normalize_usage_with_reasoning_tokens():
    result = chat._normalize_usage(
        {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "reasoning_tokens": 3, "total_tokens": 18}},
        "text",
        [],
    )
    assert result["prompt_tokens"] == 10
    assert result["completion_tokens"] == 5
    assert result["total_tokens"] == 18
    assert result["reasoning_tokens"] == 3


def test_normalize_usage_estimates_when_missing():
    """usage 缺 prompt/completion → 用估算。"""
    result = chat._normalize_usage({}, "", [{"role": "user", "content": "x"}])
    # prompt = 估算（len(json)//4），completion = 0
    assert result["prompt_tokens"] > 0
    assert result["completion_tokens"] == 0
    assert result["total_tokens"] == result["prompt_tokens"]


def test_normalize_usage_reasoning_in_raw_even_if_zero():
    """raw 含 reasoning_tokens 字段（即使 0）→ usage 也带 reasoning_tokens。"""
    result = chat._normalize_usage({"usage": {"reasoning_tokens": 0}}, "x", [])
    assert result["reasoning_tokens"] == 0


def test_int_usage_picks_first_available_key():
    assert chat._int_usage({"a": 5, "b": 10}, "a", "b") == 5
    assert chat._int_usage({"b": 10}, "a", "b") == 10
    assert chat._int_usage({}, "a", "b") is None


def test_int_usage_invalid_returns_none():
    assert chat._int_usage({"a": "not-int"}, "a") is None


def test_result_parts_extracts_fields():
    result = {"text": "hi", "reasoning": "think", "tool_calls": [{"id": 1}], "finish_reason": "stop"}
    text, reasoning, tool_calls, finish = chat._result_parts(result)
    assert text == "hi"
    assert reasoning == "think"
    assert tool_calls == [{"id": 1}]
    assert finish == "stop"


def test_result_parts_defaults_for_missing():
    text, reasoning, tool_calls, finish = chat._result_parts({})
    assert text == ""
    assert reasoning == ""
    assert tool_calls == []
    assert finish == "stop"


def test_sse_data_format():
    out = chat._sse_data({"a": 1})
    assert out.startswith("data: ")
    assert out.endswith("\n\n")
    assert json.loads(out.removeprefix("data: ").strip()) == {"a": 1}


def test_openai_chunk_shape():
    chunk = chat._openai_chunk("rid", "model", 123, {"role": "assistant"}, finish_reason="stop")
    assert chunk["id"] == "rid"
    assert chunk["object"] == "chat.completion.chunk"
    assert chunk["choices"][0]["delta"] == {"role": "assistant"}
    assert chunk["choices"][0]["finish_reason"] == "stop"


def test_openai_response_with_reasoning_and_tool_calls():
    resp = chat._openai_response(
        "model",
        "text",
        "reasoning",
        [{"id": "c1", "function": {"name": "f", "arguments": "{}"}}],
        "tool_calls",
        {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    )
    msg = resp["choices"][0]["message"]
    assert msg["content"] == "text"
    assert msg["reasoning_content"] == "reasoning"
    assert msg["tool_calls"][0]["id"] == "c1"
    assert resp["usage"]["total_tokens"] == 3


def test_anthropic_stop_reason_with_tool_calls():
    assert chat._anthropic_stop_reason("tool_calls", []) == "tool_use"
    assert chat._anthropic_stop_reason("stop", [{"id": 1}]) == "tool_use"
    assert chat._anthropic_stop_reason("stop", []) == "end_turn"


def test_anthropic_content_with_invalid_tool_args():
    """tool arguments 非合法 JSON → 回退空 dict。"""
    content = chat._anthropic_content(
        "",
        "",
        [
            {"id": "c1", "function": {"name": "f", "arguments": "not-json"}},
        ],
    )
    assert len(content) == 1
    assert content[0]["type"] == "tool_use"
    assert content[0]["input"] == {}


def test_anthropic_content_empty_returns_default():
    content = chat._anthropic_content("", "", [])
    assert content == [{"type": "text", "text": ""}]


def test_chat_model_public_shape():
    spec = ModelSpec(
        id="m1",
        provider="p",
        upstream_model="up",
        capabilities=(CAP_CHAT,),
        meta={"context_window": 8, "pricePerMTok": 1.0, "messageLimit": 5, "cheaperFallbackId": "m0"},
    )
    out = chat._chat_model_public(spec)
    assert out["id"] == "m1"
    assert out["context_window"] == 8
    assert out["price_per_mtok"] == 1.0
    assert out["message_limit"] == 5
    assert out["cheaper_fallback_id"] == "m0"
    assert out["provider"] == "p"


# ── 流式 Anthropic ──────────────────────────────────
@pytest.mark.asyncio
async def test_anthropic_stream_emits_blocks(app, fake_provider):
    fake_provider.events = [
        {"type": "text", "text": "ans"},
        {"type": "reasoning", "text": "why"},
        {"type": "usage", "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}},
        {"type": "finish", "finish_reason": "stop"},
    ]
    resp = await request(
        app,
        "POST",
        "/v1/messages",
        json={"model": MODEL, "messages": [{"role": "user", "content": "Hi"}], "stream": True, "max_tokens": 100},
    )
    assert resp.status_code == 200
    text = resp.text
    assert "message_start" in text
    assert "content_block_start" in text
    assert "content_block_delta" in text
    assert "content_block_stop" in text
    assert "message_delta" in text
    assert "message_stop" in text
    # 含 thinking 切换（reasoning → 先 stop text block 再 start thinking）
    assert "thinking_delta" in text


@pytest.mark.asyncio
async def test_anthropic_stream_tool_call(app, fake_provider):
    fake_provider.events = [
        {"type": "tool_call", "id": "c1", "name": "search", "arguments": '{"q":"x"}'},
        {"type": "usage", "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
        {"type": "finish", "finish_reason": "tool_calls"},
    ]
    resp = await request(
        app,
        "POST",
        "/v1/messages",
        json={"model": MODEL, "messages": [{"role": "user", "content": "Hi"}], "stream": True, "max_tokens": 100},
    )
    assert resp.status_code == 200
    # stop_reason 应为 tool_use
    assert "tool_use" in resp.text


@pytest.mark.asyncio
async def test_openai_stream_server_error_frame(app, fake_provider):
    """流式中 provider 抛异常 → 发 server_error 帧后 [DONE]。"""

    class _BoomProvider(FakeChatProvider):
        def chat_stream(self, model, messages, **kwargs):
            async def it():
                yield {"type": "text", "text": "partial"}
                raise RuntimeError("boom")

            return it()

    fake_provider.events = []
    monkeypatch_provider = _BoomProvider()
    # 替换 registry 中的 provider
    registry.chat_providers["tryingopen"] = monkeypatch_provider
    resp = await request(
        app,
        "POST",
        "/v1/chat/completions",
        json={"model": MODEL, "messages": [{"role": "user", "content": "Hi"}], "stream": True},
    )
    assert resp.status_code == 200
    assert "server_error" in resp.text
    assert resp.text.rstrip().endswith("data: [DONE]")


@pytest.mark.asyncio
async def test_anthropic_stream_error_frame(app, fake_provider):
    """Anthropic 流式 provider 抛异常 → 发 error 事件后 message_stop。"""

    class _BoomProvider(FakeChatProvider):
        def chat_stream(self, model, messages, **kwargs):
            async def it():
                yield {"type": "text", "text": "x"}
                raise RuntimeError("boom")

            return it()

    monkeypatch_provider = _BoomProvider()
    registry.chat_providers["tryingopen"] = monkeypatch_provider
    resp = await request(
        app,
        "POST",
        "/v1/messages",
        json={"model": MODEL, "messages": [{"role": "user", "content": "Hi"}], "stream": True, "max_tokens": 100},
    )
    assert resp.status_code == 200
    assert "api_error" in resp.text
    assert "message_stop" in resp.text


# ── chat_auth_status 管理员取完整 key ──────────────────
@pytest.mark.asyncio
async def test_chat_auth_status_admin_gets_full_key(app, monkeypatch):
    """启用鉴权 + 携带有效管理 Key → 返回完整 key。"""
    from api.routes import chat as chat_mod

    def fake_admin_enabled():
        return True

    def fake_auth_enabled():
        return True

    def fake_check_admin_key(request, scope=None):
        return True  # 管理员通过

    def fake_first_key():
        return "sk-full-key-1234567890"

    def fake_public_keymask():
        return "sk-full-***"

    monkeypatch.setattr(chat_mod.auth, "auth_enabled", fake_auth_enabled)
    monkeypatch.setattr(chat_mod.auth, "admin_enabled", fake_admin_enabled)
    monkeypatch.setattr(chat_mod, "AppError", AppError)
    # patch 函数内部 from ..auth import
    import api.auth as auth_mod

    monkeypatch.setattr(auth_mod, "first_key", fake_first_key, raising=False)
    monkeypatch.setattr(auth_mod, "public_keymask", fake_public_keymask, raising=False)
    monkeypatch.setattr(auth_mod, "check_admin_key", fake_check_admin_key, raising=False)
    monkeypatch.setattr(auth_mod, "admin_enabled", fake_admin_enabled, raising=False)

    resp = await request(app, "GET", "/v1/chat/auth/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["admin_enabled"] is True
    assert body["key"] == "sk-full-key-1234567890"


@pytest.mark.asyncio
async def test_chat_auth_status_anonymous_no_full_key(app, monkeypatch):
    """启用鉴权但匿名（check_admin_key 抛 AppError）→ key 为空。"""
    from api.routes import chat as chat_mod

    def fake_auth_enabled():
        return True

    def fake_check_admin_key(request, scope=None):
        raise AppError("SYS", "unauthorized", 401)

    def fake_first_key():
        return "sk-secret"

    def fake_public_keymask():
        return "sk-sec***"

    def fake_admin_enabled():
        return True

    monkeypatch.setattr(chat_mod.auth, "auth_enabled", fake_auth_enabled)
    monkeypatch.setattr(chat_mod.auth, "admin_enabled", fake_admin_enabled)
    monkeypatch.setattr(chat_mod, "AppError", AppError)
    import api.auth as auth_mod

    monkeypatch.setattr(auth_mod, "first_key", fake_first_key, raising=False)
    monkeypatch.setattr(auth_mod, "public_keymask", fake_public_keymask, raising=False)
    monkeypatch.setattr(auth_mod, "check_admin_key", fake_check_admin_key, raising=False)
    monkeypatch.setattr(auth_mod, "admin_enabled", fake_admin_enabled, raising=False)

    resp = await request(app, "GET", "/v1/chat/auth/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["key"] == ""  # 匿名不泄完整 key
    assert body["key_mask"] == "sk-sec***"


@pytest.mark.asyncio
async def test_chat_auth_status_open_mode(app, monkeypatch):
    """未启用鉴权（开放模式）→ key 为空。"""
    from api.routes import chat as chat_mod

    def fake_auth_enabled():
        return False

    def fake_admin_enabled():
        return False

    monkeypatch.setattr(chat_mod.auth, "auth_enabled", fake_auth_enabled)
    monkeypatch.setattr(chat_mod.auth, "admin_enabled", fake_admin_enabled)
    resp = await request(app, "GET", "/v1/chat/auth/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["key"] == ""


@pytest.mark.asyncio
async def test_chat_remaining_endpoint(app, monkeypatch):
    """/v1/chat/remaining 委托 chat_usage.remaining_credits。"""
    from api.routes import chat as chat_mod

    called = []

    async def fake_remaining():
        called.append(1)
        return {"credits": 100}

    monkeypatch.setattr(chat_mod.chat_usage, "remaining_credits", fake_remaining)
    resp = await request(app, "GET", "/v1/chat/remaining")
    assert resp.status_code == 200
    assert resp.json() == {"credits": 100}
    assert called == [1]


@pytest.mark.asyncio
async def test_chat_usage_endpoint(app, monkeypatch):
    """/v1/chat/usage 委托 chat_usage.stats。"""
    from api.routes import chat as chat_mod

    async def fake_stats(period):
        return {"period": period, "calls": 5}

    monkeypatch.setattr(chat_mod.chat_usage, "stats", fake_stats)
    resp = await request(app, "GET", "/v1/chat/usage?period=1h")
    assert resp.status_code == 200
    body = resp.json()
    assert body["period"] == "1h"
    assert body["calls"] == 5


@pytest.mark.asyncio
async def test_chat_models_endpoint(app, fake_provider, monkeypatch):
    """/v1/chat/models 返回模型列表。"""
    resp = await request(app, "GET", "/v1/chat/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 1
    assert any(m["id"] == MODEL for m in body["items"])


@pytest.mark.asyncio
async def test_chat_collect_provider_exception_503(app, fake_provider, monkeypatch):
    """_chat_collect provider 抛非 AppError 异常 → 503 + 记录失败用量。"""
    records = []

    async def record(**kwargs):
        records.append(kwargs)

    monkeypatch.setattr(chat.chat_usage, "record", record)

    class _BoomProvider(FakeChatProvider):
        async def chat_collect(self, model, messages, **kwargs):
            raise RuntimeError("provider boom")

    boom = _BoomProvider()
    registry.chat_providers["tryingopen"] = boom

    resp = await request(
        app,
        "POST",
        "/v1/chat/completions",
        json={"model": MODEL, "messages": [{"role": "user", "content": "Hi"}]},
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "PROV.001"
    # 失败用量被记录
    assert any(r.get("success") is False for r in records)


@pytest.mark.asyncio
async def test_record_swallows_chat_usage_exception(app, monkeypatch):
    """_record 内部 chat_usage.record 抛异常时被吞（不外泄到响应）。"""

    async def boom_record(**kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(chat.chat_usage, "record", boom_record)

    resp = await request(
        app,
        "POST",
        "/v1/chat/completions",
        json={"model": MODEL, "messages": [{"role": "user", "content": "Hi"}]},
    )
    # 即使 record 抛异常，主流程仍应正常返回 200（record 失败被吞）
    assert resp.status_code == 200
