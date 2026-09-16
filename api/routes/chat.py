"""OpenAI/Anthropic 兼容聊天端点。"""

from __future__ import annotations

import inspect
import json
import logging
import time
import uuid
from collections.abc import Sequence
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import auth
from ..chat_usage import chat_usage_tracker as chat_usage
from ..errors import AppError, ErrorCodes
from ..providers.base import ChatProvider, ProviderRateLimited
from ..providers.registry import bootstrap as providers_bootstrap
from ..providers.registry import registry
from ..vector.store import get_vector_store  # noqa: F401  (v11.0.0 RAG：导出给测试 mock 用)

router = APIRouter()
log = logging.getLogger("imagefree_api.chat")

# v11.0.0 RAG 增强开关（默认关闭；IF_RAG_ENABLED=1 时 chat 在 system 前注入向量检索上下文）。
# 测试可通过 patch chat_mod._rag_flag_override 强制会话内开关（避免 setenv+reset 的异步时序泄漏）。
_rag_flag_override: bool | None = None


def _rag_enabled() -> bool:
    """读取 IF_RAG_ENABLED（走 config 工厂，setenv+reset_settings 后生效）。"""
    if _rag_flag_override is not None:
        return _rag_flag_override
    try:
        from ..config import get_settings

        return bool(getattr(get_settings(), "if_rag_enabled", False))
    except Exception:
        return False


async def _rag_prefix_if_enabled(query: str) -> str:
    """IF_RAG_ENABLED=1：用向量存储检索与 query 相似的历史素材，拼成 system 前缀。

    返回空前串表示关闭或无结果（零行为变化）。Mock/异常一律降级空串，不崩 chat 主链路。
    """
    if not _rag_enabled():
        return ""
    try:
        from ..vector import embed as _embed
        from ..vector.store import get_vector_store

        store = get_vector_store()
        dup = await store.find_duplicate(_embed.compute_embedding(query or ""), threshold=0.3)
        if not dup:
            return ""
        sim = round(float(dup.get("similarity", 0.0)), 4)
        return f"[知识库检索] 参考素材 {dup.get('task_id', '')}（相似度 {sim}）：主题相关性高，可沿用其风格/构图。"
    except Exception as exc:  # noqa: BLE001 — RAG 增强是可选能力，失败降级不崩聊天
        log.warning("chat RAG 检索降级: %s", exc)
        return ""

# ── v16 P0-2：聊天工具执行回路（网关侧安全执行白名单工具 + role:tool 回填）──────

_FALLBACK_RETRY_ABLE = {"stop", "end_turn", ""}


def _tool_loop_enabled() -> bool:
    """IF_CHAT_TOOL_LOOP 是否开启（缺省 0 = 旧纯转发零行为变化）。"""
    try:
        from ..config import get_settings

        return bool(getattr(get_settings(), "if_chat_tool_loop", False))
    except Exception:
        return False


def _tool_loop_max_turns() -> int:
    try:
        from ..config import get_settings

        return int(getattr(get_settings(), "if_chat_tool_max_turns", 2))
    except Exception:
        return 2


async def _run_local_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """网关侧安全执行白名单工具（复用 MCP tools 同一份实现，不复制逻辑）。

    - 复用 `api/mcp/tools.py` 的 find_tool + guard_and_run（预算门禁 enforce 402 语义）
    - 复用 `api/agent/guard.py` 的 is_destructive_command 白名单先行拒绝（工具名命中即拒，
      不给 handler 执行机会）
    - 返回 {tool, ok, content, error} 统一信封（消费方勿抛上层，失败回填为文本）
    """
    from ..agent.guard import is_destructive_command
    from ..mcp.tools import build_tools, find_tool, guard_and_run

    if is_destructive_command(tool_name):
        return {"tool": tool_name, "ok": False, "content": "", "error": f"工具「{tool_name}」属危险命令，已拒绝执行"}
    tool = find_tool(build_tools(), tool_name)
    if tool is None:
        return {"tool": tool_name, "ok": False, "content": "", "error": f"未知工具：{tool_name}"}
    try:
        result = await guard_and_run(tool, arguments)
        text = result if isinstance(result, str) else str(result)
        return {"tool": tool_name, "ok": True, "content": text, "error": ""}
    except Exception as exc:  # noqa: BLE001 — 工具异常回填为可读文本，不崩 chat
        log.warning("chat 工具 %s 执行异常: %s", tool_name, exc)
        return {"tool": tool_name, "ok": False, "content": "", "error": f"工具执行失败：{exc}"}


def _tool_call_name(call: dict[str, Any]) -> str:
    func = call.get("function") or {}
    name = func.get("name") or ""
    # Anthropic tool_use 形态：call 直接含 name
    return name or str(call.get("name") or "")


def _tool_call_args(call: dict[str, Any]) -> dict[str, Any]:
    func = call.get("function") or {}
    raw = func.get("arguments") or call.get("input") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _tool_call_id(call: dict[str, Any]) -> str:
    return str(call.get("id") or call.get("tool_call_id") or f"call_{uuid.uuid4().hex[:12]}")


async def _build_tool_messages(
    messages: list[dict[str, Any]], tool_calls: list[dict[str, Any]], assistant_content: str | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """执行白名单工具并回填 role:tool 消息。

    返回 (扩展后的 messages, 执行结果列表)。已执行的工具结果以 OpenAI tool 角色回填；
    预算/拒绝的失败也回填为可读文本（不静默）。白名单 = MCP 五工具 + task_status。

    H1 协议修复（审查）：OpenAI 要求 role:tool 消息必须前置对应的 assistant tool_calls 声明
    ——本函数先把第一轮模型的工具声明（assistant 消息）插入，再追加各 tool 结果消息，
    否则第 2 轮续跑上游会以「messages with role 'tool' must be a response to a preceding
    message with 'tool_calls'」拒绝（或模型丢失"自己刚声明过工具调用"的上下文）。
    """
    from ..mcp.tools import TOOL_PROVIDER_MAP

    extra: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for call in tool_calls:
        name = _tool_call_name(call)
        if name not in TOOL_PROVIDER_MAP:
            # 白名单外工具：不执行，仅以可读文本回填（保持对话连贯，不裸转发半截）
            extra.append(
                {
                    "role": "tool",
                    "tool_call_id": _tool_call_id(call),
                    "content": json.dumps(
                        {"ok": False, "error": f"工具不在白名单：{name}（仅开放 {sorted(TOOL_PROVIDER_MAP)}）"},
                        ensure_ascii=False,
                    ),
                }
            )
            results.append({"tool": name, "ok": False, "content": "", "error": "not in whitelist"})
            continue
        out = await _run_local_tool(name, _tool_call_args(call))
        results.append(out)
        text = out["content"] if out["ok"] else (out["error"] or "执行失败")
        extra.append({"role": "tool", "tool_call_id": _tool_call_id(call), "content": text})
    # H1：先回填本轮 assistant 的工具声明消息（在全部 tool 结果之前）
    assistant_msg: dict[str, Any] = {
        "role": "assistant",
        "content": assistant_content or None,
        "tool_calls": tool_calls,
    }
    return messages + [assistant_msg] + extra, results


_ROLE = Literal["user", "assistant", "system", "tool"]
_REASONING_EFFORT = {
    "minimal": "quick",
    "low": "quick",
    "quick": "quick",
    "medium": "balanced",
    "balanced": "balanced",
    "none": "balanced",
    "": "balanced",
    "high": "deep",
    "max": "deep",
    "ultra": "deep",
    "deep": "deep",
}


class ChatMessage(BaseModel):
    role: _ROLE
    content: str | list[Any] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class ChatCompletionsRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    # 宽容接受任意取值（minimal/low/medium/high/max 等），未知值静默落回 balanced，
    # 避免 OpenAI 客户端（如 Cherry Studio 默认发 max）因枚举校验被 422 拒绝
    reasoning_effort: str | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None
    stream_options: dict[str, Any] | None = None


class AnthropicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[Any] | None = None


class MessagesRequest(BaseModel):
    model: str
    messages: list[AnthropicMessage]
    system: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None


def _messages_payload(messages: Sequence[BaseModel]) -> list[dict[str, Any]]:
    return [message.model_dump(exclude_none=True) for message in messages]
def _openai_effort(value: str | None) -> str:
    if not value:
        return "balanced"
    return _REASONING_EFFORT.get(str(value).strip().lower(), "balanced")


def _provider_kwargs(request: BaseModel) -> dict[str, Any]:
    values = request.model_dump(exclude_none=True)
    values.pop("model", None)
    values.pop("messages", None)
    values.pop("stream", None)
    values.pop("reasoning_effort", None)
    values.pop("stream_options", None)
    values["effort"] = _openai_effort(getattr(request, "reasoning_effort", None))
    return values


def _provider_for(model: str) -> ChatProvider:
    providers_bootstrap()
    spec = registry.chat_model(model)
    if spec is None:
        raise AppError(ErrorCodes.NOT_FOUND, f"聊天模型不存在：{model}", 404)
    prefix = model.split("/", 1)[0]
    provider = registry.chat_providers.get(prefix)
    if provider is None:
        raise AppError(ErrorCodes.PROVIDER_DOWN, f"聊天提供商不可用：{prefix}", 503)
    return provider


def _estimate_prompt_tokens(messages: list[dict[str, Any]]) -> int:
    raw = json.dumps(messages, ensure_ascii=False, separators=(",", ":"), default=str)
    return len(raw) // 4


def _int_usage(usage: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = usage.get(key)
        if value is not None:
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                return None
    return None


def _normalize_usage(result: dict[str, Any], text: str, messages: list[dict[str, Any]]) -> dict[str, int]:
    raw = result.get("usage") or {}
    prompt = _int_usage(raw, "prompt_tokens", "input_tokens")
    completion = _int_usage(raw, "completion_tokens", "output_tokens")
    reasoning = _int_usage(raw, "reasoning_tokens")
    prompt = _estimate_prompt_tokens(messages) if prompt is None else prompt
    completion = len(text) // 4 if completion is None else completion
    reasoning = 0 if reasoning is None else reasoning
    total = _int_usage(raw, "total_tokens")
    if total is None:
        total = prompt + completion + reasoning
    usage = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }
    if reasoning or "reasoning_tokens" in raw:
        usage["reasoning_tokens"] = reasoning
    return usage


def _result_parts(result: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]], str]:
    text = str(result.get("text") or "")
    reasoning = str(result.get("reasoning") or "")
    tool_calls = result.get("tool_calls") or []
    finish_reason = str(result.get("finish_reason") or "stop")
    return text, reasoning, tool_calls, finish_reason


async def _record(**kwargs: Any) -> None:
    try:
        outcome = chat_usage.record(**kwargs)
        if inspect.isawaitable(outcome):
            await outcome
    except Exception:
        log.exception("聊天用量记录失败")


def _record_args(
    provider: str,
    model: str,
    usage: dict[str, int],
    duration_ms: float,
    success: bool,
    tool_calls_count: int,
    error: str | None = None,
    proxy_used: str | None = None,
    cost_usd: float | None = None,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "reasoning_tokens": usage.get("reasoning_tokens", 0),
        "cost_usd": float(cost_usd or 0.0),
        "tool_calls_count": tool_calls_count,
        "duration_ms": duration_ms,
        "success": success,
        "proxy_used": proxy_used,
        "error": error,
    }


def _sse_data(payload: Any) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


def _openai_chunk(
    response_id: str,
    model: str,
    created: int,
    delta: dict[str, Any],
    finish_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


async def _chat_collect(
    request: ChatCompletionsRequest | MessagesRequest,
    messages: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, str, list[dict[str, Any]], str, dict[str, int]]:
    provider = _provider_for(request.model)
    provider_name = request.model.split("/", 1)[0]
    started = time.perf_counter()
    try:
        result = await provider.chat_collect(
            request.model,
            messages,
            **_provider_kwargs(request),
        )
        text, reasoning, tool_calls, finish_reason = _result_parts(result)
        usage = _normalize_usage(result, text, messages)
        await _record(
            **_record_args(
                provider_name,
                request.model,
                usage,
                (time.perf_counter() - started) * 1000,
                True,
                len(tool_calls),
                proxy_used=result.get("proxy_used"),
                cost_usd=result.get("cost_usd"),
            )
        )
        return result, text, reasoning, tool_calls, finish_reason, usage
    except AppError:
        raise
    except ProviderRateLimited as exc:
        # v7.6 P1：保留 429 限流语义（原 except Exception 把它降级为 503 PROVIDER_DOWN，
        # 客户端无法区分"可重试限流"与"提供商宕机"，错误地按 503 退避而非 Retry-After）。
        usage = _normalize_usage({}, "", messages)
        await _record(
            **_record_args(
                provider_name,
                request.model,
                usage,
                (time.perf_counter() - started) * 1000,
                False,
                0,
                error=str(exc),
            )
        )
        raise AppError(ErrorCodes.RATE_LIMITED, str(exc) or "提供商限流，请稍后重试", 429) from exc
    except Exception as exc:
        # 根因必须落日志（此前被静默吞掉导致线上排障困难）
        log.exception("聊天提供商调用失败 model=%s provider=%s", request.model, provider_name)
        usage = _normalize_usage({}, "", messages)
        await _record(
            **_record_args(
                provider_name,
                request.model,
                usage,
                (time.perf_counter() - started) * 1000,
                False,
                0,
                error=str(exc),
            )
        )
        raise AppError(ErrorCodes.PROVIDER_DOWN, "聊天提供商调用失败", 503) from exc


def _openai_response(
    model: str,
    text: str,
    reasoning: str,
    tool_calls: list[dict[str, Any]],
    finish_reason: str,
    usage: dict[str, int],
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": text or None}
    if reasoning:
        message["reasoning_content"] = reasoning
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": usage,
    }


async def _openai_stream(
    request: ChatCompletionsRequest,
    messages: list[dict[str, Any]],
    provider: ChatProvider,
) -> Any:
    response_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    provider_name = request.model.split("/", 1)[0]
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    pending_usage: dict[str, Any] = {}
    finish_reason = "stop"
    started = time.perf_counter()
    try:
        yield _sse_data(_openai_chunk(response_id, request.model, created, {"role": "assistant"}))
        stream = provider.chat_stream(request.model, messages, **_provider_kwargs(request))
        async for event in stream:
            event_type = event.get("type")
            if event_type == "text":
                text = str(event.get("text") or "")
                text_parts.append(text)
                yield _sse_data(_openai_chunk(response_id, request.model, created, {"content": text}))
            elif event_type == "reasoning":
                text = str(event.get("text") or "")
                reasoning_parts.append(text)
                yield _sse_data(_openai_chunk(response_id, request.model, created, {"reasoning_content": text}))
            elif event_type == "tool_call":
                call = {
                    "index": len(tool_calls),
                    "id": event.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                    "type": "function",
                    "function": {
                        "name": str(event.get("name") or ""),
                        "arguments": str(event.get("arguments") or "{}"),
                    },
                }
                tool_calls.append(call)
                yield _sse_data(_openai_chunk(response_id, request.model, created, {"tool_calls": [call]}))
            elif event_type == "usage":
                pending_usage = event.get("usage") or {}
            elif event_type == "finish":
                finish_reason = str(event.get("finish_reason") or finish_reason)
                yield _sse_data(_openai_chunk(response_id, request.model, created, {}, finish_reason=finish_reason))
        usage = _normalize_usage({"usage": pending_usage}, "".join(text_parts), messages)
        if (request.stream_options or {}).get("include_usage"):
            usage_chunk = _openai_chunk(response_id, request.model, created, {})
            usage_chunk["choices"] = []
            usage_chunk["usage"] = usage
            yield _sse_data(usage_chunk)
        await _record(
            **_record_args(
                provider_name,
                request.model,
                usage,
                (time.perf_counter() - started) * 1000,
                True,
                len(tool_calls),
            )
        )
    except Exception as exc:
        usage = _normalize_usage({"usage": pending_usage}, "".join(text_parts), messages)
        await _record(
            **_record_args(
                provider_name,
                request.model,
                usage,
                (time.perf_counter() - started) * 1000,
                False,
                len(tool_calls),
                error=str(exc),
            )
        )
        # v7.7 P2：流式路径区分 429（对齐 _chat_collect v7.6 修复，客户端可按 429 退避）
        if isinstance(exc, ProviderRateLimited):
            yield _sse_data({"error": {"type": "rate_limit_error", "message": str(exc) or "上游限流", "code": "PROV.001"}})
        else:
            yield _sse_data({"error": {"type": "server_error", "message": "聊天流式调用失败"}})
    finally:
        yield "data: [DONE]\n\n"


async def _collect_with_tool_loop(
    request: ChatCompletionsRequest | MessagesRequest,
    messages: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, str, list[dict[str, Any]], str, dict[str, int]]:
    """非流式聊天收集：IF_CHAT_TOOL_LOOP=1 时执行白名单工具并续跑一次汇总（最多 N 轮）。

    返回最后一次 _chat_collect 的结果（终态为 stop/end_turn 或达轮次上限）。
    未开启（缺省）→ 直接走原 _chat_collect 单轮，零行为变化。
    """
    if not _tool_loop_enabled():
        return await _chat_collect(request, messages)

    turn = 0
    max_turns = max(1, _tool_loop_max_turns())
    while turn < max_turns:
        result, text, reasoning, tool_calls, finish_reason, usage = await _chat_collect(request, messages)
        if not tool_calls or finish_reason in _FALLBACK_RETRY_ABLE:
            return result, text, reasoning, tool_calls, finish_reason, usage
        # 有工具声明 → 执行白名单工具 + 回填 role:tool 消息（H1：含前置 assistant tool_calls 声明）
        messages, _results = await _build_tool_messages(messages, tool_calls, text)
        turn += 1
    # 达轮次上限：返回最后一次结果（含工具声明，客户端可自行决定）
    return result, text, reasoning, tool_calls, finish_reason, usage


@router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionsRequest, raw_request: Request):
    auth.guard_chat_request(raw_request)
    messages = _messages_payload(request.messages)
    # v11.0.0 RAG 增强：IF_RAG_ENABLED=1 时把检索上下文拼进 system（默认关闭零变化）
    rag_prefix = await _rag_prefix_if_enabled(messages[0] if messages else "")
    if rag_prefix:
        messages = [{"role": "system", "content": rag_prefix}] + messages
    provider = _provider_for(request.model)
    if request.stream:
        return StreamingResponse(
            _openai_stream(request, messages, provider),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    _, text, reasoning, tool_calls, finish_reason, usage = await _collect_with_tool_loop(request, messages)
    return _openai_response(request.model, text, reasoning, tool_calls, finish_reason, usage)


def _anthropic_stop_reason(finish_reason: str, tool_calls: list[dict[str, Any]]) -> str:
    return "tool_use" if finish_reason == "tool_calls" or tool_calls else "end_turn"


def _anthropic_content(text: str, reasoning: str, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text})
    if reasoning:
        content.append({"type": "thinking", "thinking": reasoning})
    for call in tool_calls:
        function = call.get("function") or {}
        try:
            tool_input = json.loads(function.get("arguments") or "{}")
        except (TypeError, ValueError):
            tool_input = {}
        content.append(
            {
                "type": "tool_use",
                "id": call.get("id") or f"toolu_{uuid.uuid4().hex[:12]}",
                "name": function.get("name") or "",
                "input": tool_input,
            }
        )
    return content or [{"type": "text", "text": ""}]


@router.post("/v1/messages")
async def messages(request: MessagesRequest, raw_request: Request):
    auth.guard_chat_request(raw_request)
    message_payload = _messages_payload(request.messages)
    if request.system:
        message_payload = [{"role": "system", "content": request.system}] + message_payload
    provider = _provider_for(request.model)
    if request.stream:
        return StreamingResponse(
            _anthropic_stream(request, message_payload, provider),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    _, text, reasoning, tool_calls, finish_reason, usage = await _collect_with_tool_loop(request, message_payload)
    return {
        "id": f"msg_{uuid.uuid4().hex}",
        "type": "message",
        "role": "assistant",
        "model": request.model,
        "content": _anthropic_content(text, reasoning, tool_calls),
        "stop_reason": _anthropic_stop_reason(finish_reason, tool_calls),
        "usage": {
            "input_tokens": usage["prompt_tokens"],
            "output_tokens": usage["completion_tokens"],
        },
    }


async def _anthropic_stream(
    request: MessagesRequest,
    messages: list[dict[str, Any]],
    provider: Any,
):
    response_id = f"msg_{uuid.uuid4().hex}"
    provider_name = request.model.split("/", 1)[0]
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    pending_usage: dict[str, Any] = {}
    finish_reason = "stop"
    active_block = "text"
    block_index = 0
    started = time.perf_counter()
    try:
        initial_usage = _normalize_usage({}, "", messages)
        yield "event: message_start\n"
        yield _sse_data(
            {
                "type": "message_start",
                "message": {
                    "id": response_id,
                    "type": "message",
                    "role": "assistant",
                    "model": request.model,
                    "content": [],
                    "usage": {"input_tokens": initial_usage["prompt_tokens"], "output_tokens": 0},
                },
            }
        )
        yield "event: content_block_start\n"
        yield _sse_data({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})
        stream = provider.chat_stream(request.model, messages, **_provider_kwargs(request))
        async for event in stream:
            event_type = event.get("type")
            if event_type == "text":
                text = str(event.get("text") or "")
                text_parts.append(text)
                yield "event: content_block_delta\n"
                yield _sse_data(
                    {
                        "type": "content_block_delta",
                        "index": block_index,
                        "delta": {"type": "text_delta", "text": text},
                    }
                )
            elif event_type == "reasoning":
                if active_block == "text":
                    yield "event: content_block_stop\n"
                    yield _sse_data({"type": "content_block_stop", "index": block_index})
                    block_index += 1
                    active_block = "thinking"
                    yield "event: content_block_start\n"
                    yield _sse_data(
                        {
                            "type": "content_block_start",
                            "index": block_index,
                            "content_block": {"type": "thinking", "thinking": ""},
                        }
                    )
                text = str(event.get("text") or "")
                reasoning_parts.append(text)
                yield "event: content_block_delta\n"
                yield _sse_data(
                    {
                        "type": "content_block_delta",
                        "index": block_index,
                        "delta": {"type": "thinking_delta", "thinking": text},
                    }
                )
            elif event_type == "usage":
                pending_usage = event.get("usage") or {}
            elif event_type == "tool_call":
                tool_calls.append(
                    {
                        "id": event.get("id"),
                        "function": {
                            "name": event.get("name") or "",
                            "arguments": event.get("arguments") or "{}",
                        },
                    }
                )
            elif event_type == "finish":
                finish_reason = str(event.get("finish_reason") or finish_reason)
        yield "event: content_block_stop\n"
        yield _sse_data({"type": "content_block_stop", "index": block_index})
        text = "".join(text_parts)
        usage = _normalize_usage({"usage": pending_usage}, text, messages)
        stop_reason = _anthropic_stop_reason(finish_reason, tool_calls)
        yield "event: message_delta\n"
        yield _sse_data(
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": usage["completion_tokens"]},
            }
        )
        await _record(
            **_record_args(
                provider_name,
                request.model,
                usage,
                (time.perf_counter() - started) * 1000,
                True,
                len(tool_calls),
            )
        )
    except Exception as exc:
        usage = _normalize_usage({"usage": pending_usage}, "".join(text_parts), messages)
        await _record(
            **_record_args(
                provider_name,
                request.model,
                usage,
                (time.perf_counter() - started) * 1000,
                False,
                len(tool_calls),
                error=str(exc),
            )
        )
        # v7.7 P2：流式路径区分 429（对齐 _chat_collect v7.6 修复）
        if isinstance(exc, ProviderRateLimited):
            yield "event: error\n"
            yield _sse_data({"type": "error", "error": {"type": "rate_limit_error", "message": str(exc) or "上游限流", "code": "PROV.001"}})
        else:
            yield "event: error\n"
            yield _sse_data({"type": "error", "error": {"type": "api_error", "message": "聊天流式调用失败"}})
    finally:
        yield "event: message_stop\n"
        yield _sse_data({"type": "message_stop"})


@router.get("/v1/chat/usage")
async def get_chat_usage(period: Literal["1h", "24h", "7d", "30d"] = Query("24h")):
    return await chat_usage.stats(period)


def _chat_model_public(spec) -> dict[str, Any]:
    """ModelSpec → 前端 / OpenAI 风格公开字段。"""
    meta = spec.meta or {}
    return {
        "id": spec.id,
        "object": "model",
        "display_name": spec.display_name or spec.upstream_model,
        "upstream_model": spec.upstream_model,
        "provider": spec.provider,
        "context_window": meta.get("context_window", 0),
        "capabilities": list(spec.capabilities),
        "price_per_mtok": meta.get("pricePerMTok"),
        "message_limit": meta.get("messageLimit", 0),
        "cheaper_fallback_id": meta.get("cheaperFallbackId", ""),
    }


@router.get("/v1/chat/models")
async def list_chat_models():
    """聊天模型目录（动态 + 静态回退合并）。"""
    providers_bootstrap()
    models = registry.all_chat_models()
    items = [_chat_model_public(m) for m in models]
    items.sort(key=lambda m: m["id"])
    return {"items": items, "count": len(items), "auth_required": auth.auth_enabled()}


@router.get("/v1/chat/auth/status")
async def chat_auth_status(request: Request):
    """鉴权状态：前端/调用方探测是否需要携带 Key。

    安全（P0）：匿名回调**只返回脱敏 key_mask + auth_enabled**，不暴露完整 key。
    仅当请求携带**管理面有效 Key**（check_admin_key 通过）时，才附带完整 key，
    供站长管理面板「一键复制」（复制按钮仅站长可见）。
    未启用鉴权（开放模式）时 key 为空。
    """
    from ..auth import admin_enabled, check_admin_key, first_key, public_keymask

    enabled = auth.auth_enabled()
    full_key = ""
    # 站长自助取完整 Key：需携带管理面有效 Key（IF_ADMIN_KEYS 或业务 Key 池）
    # 捕获 AppError（401/403 = 鉴权未通过），full_key 保持空 → 匿名不泄完整 key；
    # 非 AppError 的真实内部错误不放行到 500，避免把故障静默吞成「无 key」。
    if enabled:
        try:
            check_admin_key(request, scope="admin-auth-status")
            full_key = first_key()
        except AppError:
            full_key = ""
    return {
        "enabled": enabled,
        "admin_enabled": admin_enabled(),
        "key_mask": public_keymask(),
        "key": full_key,
        "header": "Authorization: Bearer <key>",
        "alt_headers": ["X-API-Key", "?api_key="],
    }


@router.get("/v1/chat/remaining")
async def get_chat_remaining():
    return await chat_usage.remaining_credits()


__all__ = ["router"]
