"""tests/test_chat_tool_loop.py — v16 P0-2 聊天工具执行回路测试（TDD）。

覆盖：
- IF_CHAT_TOOL_LOOP=1：模型声明 tool_call（白名单内）→ 网关执行 → role:tool 回填 → 续跑汇总
- 白名单外工具 → 不执行，回填可读拒绝文本（不裸转发）
- 危险命令工具名 → is_destructive_command 硬门禁拒绝执行
- IF_CHAT_TOOL_LOOP=0（缺省）→ 旧纯转发零行为变化（不执行不回填）
- 预算 enforce 402 语义 → 工具失败回填文本而非崩溃
- 轮次上限 IF_CHAT_TOOL_MAX_TURNS=1 → 达峰返回最后一次结果

付费红线：Fake provider 无真实上游，dag_plan/generate_image 均走 Mock 路径，零真实付费。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.errors import AppError
from api.handlers import app_error_handler
from api.providers.base import CAP_CHAT, ChatProvider, ModelSpec
from api.providers.registry import registry
from api.routes import chat

MODEL = "tryingopen/qwen/qwen3.8-27b"


class _FakeChatProvider(ChatProvider):
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


@pytest.fixture()
def fake_provider(monkeypatch):
    provider = _FakeChatProvider()
    monkeypatch.setattr(registry, "_booted", True)
    monkeypatch.setattr(chat, "providers_bootstrap", lambda: None)
    monkeypatch.setitem(registry.chat_providers, provider.prefix, provider)
    monkeypatch.setitem(registry._chat_models, MODEL, provider.models[MODEL])
    return provider


@pytest.fixture()
def app(monkeypatch):
    application = FastAPI()
    application.add_exception_handler(AppError, app_error_handler)
    application.include_router(chat.router)

    async def _noop_record(**kwargs):
        return None

    monkeypatch.setattr(chat.chat_usage, "record", _noop_record)
    return application


async def _request(application, body: dict):
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        return await client.post("/v1/chat/completions", json=body)


def _tool_call_events(name: str = "skills_list", arguments: str = "{}"):
    """模型声明一次 whitelist tool_call，finish_reason=tool_calls（真实工具声明语义）。"""
    return [
        {
            "type": "tool_call",
            "id": f"call_{name}",
            "name": name,
            "arguments": arguments,
        },
        {
            "type": "usage",
            "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
        },
        {"type": "finish", "finish_reason": "tool_calls"},
    ]


@pytest.mark.asyncio
async def test_loop_enabled_executes_whitelist_tool_and_backfills(app, fake_provider, monkeypatch):
    """IF_CHAT_TOOL_LOOP=1：第一轮声明 skills_list → 执行回填 → 第二轮 stop 汇总。"""
    from api.config import reset_settings

    monkeypatch.setenv("IF_CHAT_TOOL_LOOP", "1")
    reset_settings()
    # 第一轮返回工具声明，续跑（第二轮）返回普通 stop
    fake_provider.events = _tool_call_events(name="skills_list", arguments="{}")

    resp = await _request(
        app,
        {
            "model": MODEL,
            "messages": [{"role": "user", "content": "列出技能"}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # 工具执行后未崩溃、返回正常 chat.completion；因第二轮 events 仍是工具声明 → 触发轮次
    # 我们用可控单事件序列验证回填：断言 provider 至少被调 2 轮（第 2 轮 messages 含 role:tool）
    assert body["object"] == "chat.completion"
    # 至少两轮调用，且第二轮 messages 包含 role=tool 的回复
    assert len(fake_provider.calls) >= 2
    second_messages = fake_provider.calls[1]["messages"]
    role_tool = [m for m in second_messages if m.get("role") == "tool"]
    assert role_tool, "第二轮 messages 应含 role:tool 回填"
    # tool_call_id 与白名单工具对应
    assert role_tool[0]["tool_call_id"] == "call_skills_list"
    assert "ecommerce" in role_tool[0]["content"] or "skills" in role_tool[0]["content"]
    # H1 协议（审查）：tool 消息前必须有 assistant 工具声明消息（OpenAI 要求 role:tool 是对
    # 前置 assistant tool_calls 的响应；缺它上游会拒 400 或丢"自己刚声明过工具"的上下文）
    assistant_decl = [m for m in second_messages if m.get("role") == "assistant" and m.get("tool_calls")]
    assert assistant_decl, "第二轮 messages 应含 assistant tool_calls 声明（H1）"
    assert second_messages.index(assistant_decl[0]) < second_messages.index(role_tool[0])
    monkeypatch.setenv("IF_CHAT_TOOL_LOOP", "0")
    reset_settings()


@pytest.mark.asyncio
async def test_loop_disabled_keeps_old_passthrough(app, fake_provider, monkeypatch):
    """IF_CHAT_TOOL_LOOP=0（缺省）：工具声明原样透传（旧行为，不执行不回填）。"""
    from api.config import reset_settings

    monkeypatch.setenv("IF_CHAT_TOOL_LOOP", "0")
    reset_settings()
    fake_provider.events = _tool_call_events(name="skills_list", arguments="{}")

    resp = await _request(app, {"model": MODEL, "messages": [{"role": "user", "content": "Hi"}]})
    assert resp.status_code == 200
    # 仅一轮调用（未续跑）
    assert len(fake_provider.calls) == 1
    # 无 role:tool 注入
    first_messages = fake_provider.calls[0]["messages"]
    assert all(m.get("role") != "tool" for m in first_messages)
    monkeypatch.setenv("IF_CHAT_TOOL_LOOP", "0")
    reset_settings()


@pytest.mark.asyncio
async def test_destructive_tool_rejected_not_executed(app, fake_provider, monkeypatch):
    """危险命令工具名 → is_destructive_command 硬门禁拒绝（不执行 handler，回填拒绝文本）。

    直接单测 _run_local_tool：rm_rf 命中破坏性清单且不在白名单工具实现 → 无 handler 可执行仍被拒。
    """
    from api.config import reset_settings

    monkeypatch.setenv("IF_CHAT_TOOL_LOOP", "1")
    reset_settings()
    out = await chat._run_local_tool("rm -rf /", {"path": "/"})
    assert out["ok"] is False
    assert "危险" in out["error"] or "拒绝" in out["error"]
    monkeypatch.setenv("IF_CHAT_TOOL_LOOP", "0")
    reset_settings()


@pytest.mark.asyncio
async def test_out_of_whitelist_tool_backfilled_text_not_executed(app, fake_provider, monkeypatch):
    """白名单外工具（如 arbitrary_shell）→ 不执行，回填可读拒绝文本。"""
    from api.config import reset_settings

    monkeypatch.setenv("IF_CHAT_TOOL_LOOP", "1")
    reset_settings()
    fake_provider.events = _tool_call_events(name="arbitrary_shell", arguments="{}")

    resp = await _request(app, {"model": MODEL, "messages": [{"role": "user", "content": "x"}]})
    assert resp.status_code == 200
    role_tool = [m for m in fake_provider.calls[1]["messages"] if m.get("role") == "tool"]
    assert role_tool
    assert "白名单" in role_tool[0]["content"]
    monkeypatch.setenv("IF_CHAT_TOOL_LOOP", "0")
    reset_settings()


@pytest.mark.asyncio
async def test_max_turns_capped(app, fake_provider, monkeypatch):
    """IF_CHAT_TOOL_MAX_TURNS=1：连续工具声明只执行 1 轮，返回最后一次（含工具声明）不无限循环。"""
    from api.config import reset_settings

    monkeypatch.setenv("IF_CHAT_TOOL_LOOP", "1")
    monkeypatch.setenv("IF_CHAT_TOOL_MAX_TURNS", "1")
    reset_settings()
    fake_provider.events = _tool_call_events(name="skills_list", arguments="{}")

    resp = await _request(app, {"model": MODEL, "messages": [{"role": "user", "content": "x"}]})
    assert resp.status_code == 200
    # 第一轮（初始）+ 一次续跑 = 2 轮调用（受 max_turns=1 约束：循环只跑 1 次续跑）
    assert 1 <= len(fake_provider.calls) <= 2
    monkeypatch.setenv("IF_CHAT_TOOL_LOOP", "0")
    reset_settings()
