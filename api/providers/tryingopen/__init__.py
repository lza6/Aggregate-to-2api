"""tryingopen.com 文本对话提供商适配（包入口）。

P0-6：原 ``api/providers/tryingopen.py``（810 行）拆为包：
- 本 ``__init__.py`` 保留 ``TryingopenChatProvider`` 类与运行时模块级绑定
  （``proxy_pool``/``asyncio``/``config``），因 ``chat_stream`` 内经模块 globals
  解析这些名字，tests/test_tryingopen.py 的 ``monkeypatch.setattr(tryingopen, ...)``
  才能命中；类不能下沉到子模块，否则 monkeypatch 失效。
- ``_helpers.py`` 提取纯辅助函数/常量/dataclass/异常（不依赖 monkeypatch 命中点）。

旧 import 路径全部保留：``from api.providers.tryingopen import TryingopenChatProvider``、
``import api.providers.tryingopen as t; t._AttemptResult`` 等均可用。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any
from urllib.parse import urljoin

import httpx

from ... import config
from ...prompts import compose_system_text
from ...proxy_pool import proxy_pool
from ..base import (
    CAP_CHAT,
    CAP_CHAT_TOOLS,
    CAP_CHAT_VISION,
    ChatProvider,
    ModelSpec,
    ProviderError,
    ProviderRateLimited,
)
from ._helpers import (
    _CHUNK_RE,
    _FALLBACK_CATALOG,
    _HTTP_TIMEOUT,
    _MODEL_RE,
    DEFAULT_BASE_URL,
    DEFAULT_EFFORT,
    OPEN_PATH,
    _AttemptResult,
    _content_text,
    _last_json_object,
    _media_type,
    _message_parts,
    _parse_context_window,
    _parse_plaintext_tool_calls,
    _resolve,
    _tool_instruction,
    _TryingopenRateLimited,
)

log = logging.getLogger("providers.tryingopen")


class TryingopenChatProvider(ChatProvider):
    prefix = "tryingopen"
    provider_prefix = prefix
    display_name = "TryingOpen"
    base_url = DEFAULT_BASE_URL
    models: dict[str, ModelSpec] = {}

    def __init__(self) -> None:
        super().__init__()
        self.models = {}
        self._client: httpx.AsyncClient | Any | None = None
        self._sync_task: asyncio.Task | None = None
        self._catalog_source = "fallback"
        self._last_sync = 0.0
        self._current_meta: dict[str, Any] | None = None  # P0-3：当前请求模型的 meta（chat_stream 设置）
        self._build_models(_FALLBACK_CATALOG)

    def _build_models(self, records: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> None:
        built: dict[str, ModelSpec] = {}
        for record in records:
            raw_id = str(record.get("id", "")).strip()
            if not raw_id or "/" not in raw_id:
                continue
            capabilities = [CAP_CHAT]
            supports_tools = bool(record.get("supportsTools"))
            supports_images = bool(record.get("supportsImages"))
            if supports_tools:
                capabilities.append(CAP_CHAT_TOOLS)
            if supports_images:
                capabilities.append(CAP_CHAT_VISION)
            context_window = _parse_context_window(record.get("context"))
            meta = {
                key: record[key]
                for key in (
                    "context",
                    "supportsTools",
                    "supportsImages",
                    "pricePerMTok",
                    "messageLimit",
                    "cheaperFallbackId",
                    # P0-3：提示词模板系统 meta 键（全部可选，向后兼容）
                    "system_prompt_template",
                    "thinking_mode",
                    "max_thinking_length",
                    "refusal_stance",
                    "citation_style",
                    "skills",
                )
                if key in record
            }
            if context_window is not None:
                meta["context_window"] = context_window
            model_id = f"{self.prefix}/{raw_id}"
            built[model_id] = ModelSpec(
                id=model_id,
                provider=self.prefix,
                upstream_model=raw_id,
                capabilities=tuple(capabilities),
                display_name=str(record.get("name") or raw_id),
                description="TryingOpen 免费文本对话",
                resolutions=(),
                credits=None,
                account_required=False,
                meta=meta,
            )
        self.models = built

    def needs_proxy_per_request(self) -> bool:
        return True

    def _convert_messages(
        self, messages: list[dict[str, Any]], tools: list[Any] | None = None, tool_choice: Any = None
    ) -> list[dict[str, Any]]:
        effective_tools = tools if tools and tool_choice != "none" else None
        source = [dict(message) for message in messages]
        if effective_tools:
            source.append({"role": "system", "content": _tool_instruction(effective_tools, tool_choice)})

        system_texts = [_content_text(m.get("content")) for m in source if m.get("role") == "system"]
        system_text = "\n\n".join(text for text in system_texts if text)
        converted: list[dict[str, Any]] = []
        for message in source:
            role = str(message.get("role", "user"))
            if role == "system":
                continue
            parts = _message_parts(message.get("content"))
            tool_calls = message.get("tool_calls")
            if role == "assistant" and isinstance(tool_calls, list) and tool_calls:
                called: list[str] = []
                for call in tool_calls:
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function") if isinstance(call.get("function"), dict) else call
                    name = function.get("name", "")
                    arguments = function.get("arguments", "{}")
                    if isinstance(arguments, (dict, list)):
                        arguments = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
                    called.append(f"{name}({arguments})")
                if called:
                    parts.append({"type": "text", "text": "[called " + "; ".join(called) + ";]"})
            # OpenAI role=tool 消息（工具结果回传）——上游只接受 user/assistant，
            # 不转换会得到 HTTP 400 "Invalid messages"。包装为函数结果标记交回模型。
            if role == "tool":
                role = "user"
                call_id = str(message.get("tool_call_id") or "unknown")
                tool_text = _content_text(message.get("content")) or "(empty result)"
                if not parts:
                    parts = [{"type": "text", "text": tool_text}]
                converted.append(
                    {
                        "id": str(message.get("id") or f"msg-{uuid.uuid4().hex[:12]}"),
                        "role": role,
                        "parts": [
                            {"type": "text", "text": f"[TOOL RESULT for {call_id}]\n{tool_text}\n[/TOOL RESULT]"},
                        ],
                    }
                )
                continue
            item_id = message.get("id") or f"msg-{uuid.uuid4().hex[:12]}"
            converted.append({"id": str(item_id), "role": role, "parts": parts})

        user_index = next((index for index, item in enumerate(converted) if item["role"] == "user"), None)
        if user_index is None:
            converted.insert(0, {"id": f"msg-{uuid.uuid4().hex[:12]}", "role": "user", "parts": []})
            user_index = 0
        # P0-3：系统提示词模板系统——按 ModelSpec.meta.system_prompt_template 组合宪法+模板+用户 system
        # 无模板键/开关关闭时 compose_system_text 原样返回 user system，向后兼容原 [SYSTEM INSTRUCTIONS] 路径
        composed_system = compose_system_text(system_text, getattr(self, "_current_meta", None))
        if composed_system:
            converted[user_index]["parts"] = [
                {"type": "text", "text": f"[SYSTEM INSTRUCTIONS]\n{composed_system}\n[/SYSTEM INSTRUCTIONS]"},
                *converted[user_index]["parts"],
            ]
        return converted

    @staticmethod
    def _payload(model: str, messages: list[dict[str, Any]], effort: str) -> dict[str, Any]:
        return {
            "id": f"chat-{uuid.uuid4().hex[:16]}",
            "trigger": "submit-message",
            "messageId": f"msg-{uuid.uuid4().hex[:24]}",
            "model": model.split("/", 1)[1] if model.startswith("tryingopen/") else model,
            "effort": effort,
            "messages": messages,
            "stream": True,  # 显式要求上游开启 SSE 增量流式，否则上游按整段返回、客户端无逐 token 体验
        }

    async def chat_stream(
        self,
        model: str,
        messages: list[dict],
        tools: list | None = None,
        tool_choice: Any = None,
        effort: str = DEFAULT_EFFORT,
        **kw: Any,
    ) -> AsyncIterator[dict]:
        # P0-3：把当前模型的 meta 暴露给 _convert_messages（用于 system_prompt_template 组合）
        spec = self.models.get(model)
        self._current_meta = spec.meta if spec else None
        converted = self._convert_messages(messages, tools, tool_choice)
        payload = self._payload(model, converted, effort)
        attempts = config.IF_TRYINGOPEN_MAX_ATTEMPTS
        # v4.4.1: N 轮代理轮换全部失败后，追加一次直连兜底（本机 IP 常比随机免费代理更稳）
        total_rounds = attempts + 1
        # 带工具调用时走聚合路径（工具是纯文本 JSON，需完整上下文才能剥离）；
        # 普通对话走「真流式增量」——上游 reasoning-delta/text-delta 逐 token 透传，
        # 客户端思考区与正文区并行增量显示，而非等模型写完才一次性返回。
        streaming = not (tools and tool_choice != "none")
        for attempt in range(total_rounds):
            is_direct_fallback = attempt >= attempts
            proxy_url = None if is_direct_fallback else await proxy_pool.acquire(prefer_source="free")
            try:
                if streaming:
                    usage: dict[str, int] | None = None
                    finish_reason = "stop"
                    async for kind, event in self._request_stream_events(payload, proxy_url):
                        if kind == "reasoning-delta":
                            delta = str(event.get("delta") or "")
                            if delta:
                                yield {"type": "reasoning", "text": delta}
                        elif kind == "text-delta":
                            delta = str(event.get("delta") or "")
                            if delta:
                                yield {"type": "text", "text": delta}
                        elif kind == "finish":
                            finish_reason = str(event.get("finishReason") or "stop")
                            usage = self._usage(event.get("messageMetadata") or {})
                            error_message = str(
                                event.get("errorText")
                                or (event.get("messageMetadata") or {}).get("errorText")
                                or (event.get("messageMetadata") or {}).get("error")
                                or ""
                            )
                            if finish_reason == "error" and error_message:
                                raise ProviderError(f"tryingopen 上游错误: {error_message[:200]}")
                        elif kind == "error":
                            raise ProviderError(
                                f"tryingopen 上游错误: {str(event.get('errorText') or 'unknown')[:200]}"
                            )
                    if usage:
                        yield {"type": "usage", "usage": usage}
                    yield {"type": "finish", "finish_reason": finish_reason or "stop"}
                else:
                    result = await _resolve(self._request_once(payload, proxy_url))
                    async for event in self._result_events(result, tools, tool_choice):
                        yield event
            except _TryingopenRateLimited as exc:
                if proxy_url:
                    await proxy_pool.mark_failure(proxy_url, rate_limited=True)
                if attempt + 1 < total_rounds:
                    await asyncio.sleep(2 ** min(attempt, 3))
                    continue
                raise ProviderRateLimited("tryingopen 全部出口限流中") from exc
            except httpx.HTTPError as exc:
                if proxy_url:
                    await proxy_pool.mark_failure(proxy_url, rate_limited=False)
                if attempt + 1 < total_rounds:
                    await asyncio.sleep(2 ** min(attempt, 3))
                    continue
                raise ProviderError(f"tryingopen 网络请求失败: {str(exc)[:160]}") from exc
            except ProviderError:
                if proxy_url:
                    await proxy_pool.mark_failure(proxy_url, rate_limited=False)
                # v4.4.1: 免费代理下的偶发上游错误同样换出口重试；
                # 仅直连兜底仍失败才最终抛出（直连时 proxy_url 为 None）
                if not is_direct_fallback and attempt + 1 < total_rounds:
                    await asyncio.sleep(2 ** min(attempt, 3))
                    continue
                raise
            if proxy_url:
                await proxy_pool.mark_success(proxy_url)
            return
        raise ProviderRateLimited("tryingopen 全部出口限流中")

    async def _request_stream_events(
        self, payload: dict[str, Any], proxy_url: str | None
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """逐行透传上游 SSE：每收到一个事件就 yield (event_type, event)，实现真增量流式。"""
        request_proxy = proxy_url or config.PROXY
        client: Any = None
        close_client = False
        if self._client is not None and request_proxy == config.PROXY:
            client = self._client
        else:
            client = httpx.AsyncClient(proxy=request_proxy, timeout=_HTTP_TIMEOUT)
            close_client = True
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "User-Agent": config.USER_AGENT,
        }
        try:
            async with client.stream("POST", f"{self.base_url}{OPEN_PATH}", headers=headers, json=payload) as response:
                status = int(getattr(response, "status_code", 200))
                if status == 429:
                    body = await self._response_body(response)
                    raise _TryingopenRateLimited(self._error_text(body))
                if status < 200 or status >= 300:
                    body = await self._response_body(response)
                    raise ProviderError(f"tryingopen HTTP {status}: {self._error_text(body)}")
                async for line in self._response_lines(response):
                    if not line:
                        continue
                    raw = line.decode("utf-8", "replace") if isinstance(line, bytes) else str(line)
                    if not raw.startswith("data:"):
                        continue
                    data = raw[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        log.debug("忽略 tryingopen 非 JSON SSE: %s", data[:200])
                        continue
                    yield (str(event.get("type") or ""), event)
        finally:
            if close_client:
                await client.aclose()

    async def _result_events(self, result: _AttemptResult, tools: list | None, tool_choice: Any) -> AsyncIterator[dict]:
        effective_tools = tools if tools and tool_choice != "none" else None
        calls: list[dict[str, str]] | None = None
        call_source = result.text
        if effective_tools:
            calls = _parse_plaintext_tool_calls(result.text)
            if calls is None:
                calls = _parse_plaintext_tool_calls(result.reasoning)
                call_source = result.reasoning
        if calls:
            if result.reasoning:
                yield {"type": "reasoning", "text": result.reasoning}
            _, position = _last_json_object(call_source)
            before = call_source[:position].strip() if position is not None else ""
            import re as _re
            before = _re.sub(r"```(?:json)?\s*$", "", before, flags=_re.IGNORECASE).strip()
            if before:
                yield {"type": "text", "text": before}
            for index, call in enumerate(calls):
                yield {
                    "type": "tool_call",
                    "id": f"call_{uuid.uuid4().hex[:16]}",
                    "name": call["name"],
                    "arguments": call["arguments"],
                }
            if result.usage:
                yield {"type": "usage", "usage": result.usage}
            yield {"type": "finish", "finish_reason": "tool_calls"}
            return
        if result.reasoning:
            yield {"type": "reasoning", "text": result.reasoning}
        if result.text:
            yield {"type": "text", "text": result.text}
        if result.usage:
            yield {"type": "usage", "usage": result.usage}
        yield {"type": "finish", "finish_reason": result.finish_reason or "stop"}

    async def _request_once(self, payload: dict[str, Any], proxy_url: str | None) -> _AttemptResult:
        request_proxy = proxy_url or config.PROXY
        client: Any = None
        close_client = False
        if self._client is not None and request_proxy == config.PROXY:
            client = self._client
        else:
            client = httpx.AsyncClient(proxy=request_proxy, timeout=_HTTP_TIMEOUT)
            close_client = True
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "User-Agent": config.USER_AGENT,
        }
        try:
            async with client.stream("POST", f"{self.base_url}{OPEN_PATH}", headers=headers, json=payload) as response:
                status = int(getattr(response, "status_code", 200))
                if status == 429:
                    body = await self._response_body(response)
                    raise _TryingopenRateLimited(self._error_text(body))
                if status < 200 or status >= 300:
                    body = await self._response_body(response)
                    raise ProviderError(f"tryingopen HTTP {status}: {self._error_text(body)}")
                return await self._parse_response(response)
        finally:
            if close_client:
                await client.aclose()

    async def _parse_response(self, response: Any) -> _AttemptResult:
        reasoning: list[str] = []
        text: list[str] = []
        usage: dict[str, int] | None = None
        finish_reason = "stop"
        stream_error: str | None = None
        async for line in self._response_lines(response):
            if not line:
                continue
            raw = line.decode("utf-8", "replace") if isinstance(line, bytes) else str(line)
            if not raw.startswith("data:"):
                continue
            data = raw[5:].strip()
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except (TypeError, ValueError, json.JSONDecodeError):
                log.debug("忽略 tryingopen 非 JSON SSE: %s", data[:200])
                continue
            event_type = event.get("type")
            if event_type == "reasoning-delta":
                reasoning.append(str(event.get("delta", "")))
            elif event_type == "text-delta":
                text.append(str(event.get("delta", "")))
            elif event_type == "finish":
                finish_reason = str(event.get("finishReason") or "stop")
                metadata = event.get("messageMetadata") or {}
                usage = self._usage(metadata)
                error_message = str(
                    event.get("errorText")
                    or metadata.get("errorText")
                    or metadata.get("error")
                    or metadata.get("message")
                    or ""
                )
                if finish_reason == "error" and error_message:
                    stream_error = error_message
            elif event_type == "error":
                stream_error = str(event.get("errorText") or "tryingopen 上游错误")
        if stream_error:
            lowered = stream_error.lower()
            if "credit" in lowered or "limit" in lowered:
                raise _TryingopenRateLimited(stream_error)
            raise ProviderError(f"tryingopen 上游错误: {stream_error[:200]}")
        return _AttemptResult("".join(reasoning), "".join(text), usage, finish_reason)

    @staticmethod
    def _usage(metadata: dict[str, Any]) -> dict[str, int] | None:
        mapping = {
            "inputTokens": "prompt_tokens",
            "outputTokens": "completion_tokens",
            "totalTokens": "total_tokens",
            "reasoningTokens": "reasoning_tokens",
        }
        usage: dict[str, int] = {}
        for source, target in mapping.items():
            value = metadata.get(source)
            if value is not None:
                try:
                    usage[target] = int(value)
                except (TypeError, ValueError):
                    continue
        return usage or None

    @staticmethod
    async def _response_lines(response: Any) -> AsyncIterator[str | bytes]:
        if hasattr(response, "aiter_lines"):
            async for line in response.aiter_lines():
                yield line
            return
        if hasattr(response, "aiter_bytes"):
            buffer = b""
            async for chunk in response.aiter_bytes():
                buffer += chunk if isinstance(chunk, bytes) else str(chunk).encode()
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    yield line.rstrip(b"\r")
            if buffer:
                yield buffer.rstrip(b"\r")

    @staticmethod
    async def _response_body(response: Any) -> str:
        if hasattr(response, "aread"):
            body = await response.aread()
        else:
            body = getattr(response, "content", b"")
        if isinstance(body, bytes):
            return body.decode("utf-8", "replace")
        return str(body)

    @staticmethod
    def _error_text(body: str) -> str:
        try:
            value = json.loads(body)
            if isinstance(value, dict):
                return str(value.get("error") or value.get("message") or body)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        return body[:240]

    async def _fetch_catalog(self) -> list[dict[str, Any]]:
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(proxy=config.PROXY, timeout=_HTTP_TIMEOUT)
        try:
            home = await client.get(f"{self.base_url}/")
            if int(getattr(home, "status_code", 200)) >= 400:
                raise ProviderError(f"tryingopen 首页 HTTP {home.status_code}")
            html = str(getattr(home, "text", ""))
            chunk_paths = list(dict.fromkeys(_CHUNK_RE.findall(html)))
            records: list[dict[str, Any]] = []
            for path in chunk_paths:
                chunk = await client.get(urljoin(f"{self.base_url}/", path))
                if int(getattr(chunk, "status_code", 200)) >= 400:
                    continue
                chunk_text = str(getattr(chunk, "text", ""))
                if "supportsTools" not in chunk_text:
                    continue
                records.extend(self._parse_catalog_chunk(chunk_text))
            if not records:
                raise ProviderError("tryingopen 未发现模型目录")
            unique: dict[str, dict[str, Any]] = {str(record["id"]): record for record in records}
            return list(unique.values())
        finally:
            if own_client:
                await client.aclose()

    @staticmethod
    def _parse_catalog_chunk(chunk: str) -> list[dict[str, Any]]:
        import re as _re
        records: list[dict[str, Any]] = []
        for match in _MODEL_RE.finditer(chunk):
            raw_id, name = match.groups()
            end = chunk.find("}", match.end())
            segment = chunk[match.start() : end if end >= 0 else min(len(chunk), match.end() + 1000)]
            record: dict[str, Any] = {"id": raw_id, "name": name}
            context = _re.search(r'context:"([^"]+)"', segment)
            if context:
                record["context"] = context.group(1)
            for key in ("supportsTools", "supportsImages"):
                if _re.search(rf"{key}:(?:!0|true)", segment):
                    record[key] = True
            price = _re.search(r"pricePerMTok:([0-9.]+)", segment)
            if price:
                record["pricePerMTok"] = float(price.group(1))
            limit = _re.search(r"messageLimit:(\d+)", segment)
            if limit:
                record["messageLimit"] = int(limit.group(1))
            fallback = _re.search(r'cheaperFallbackId:"([^"]+)"', segment)
            if fallback:
                record["cheaperFallbackId"] = fallback.group(1)
            records.append(record)
        return records

    async def refresh_models(self) -> int:
        try:
            records = await _resolve(self._fetch_catalog())
            old_models = self.models
            self._build_models(records)
            self.models = {**old_models, **self.models}
            self._catalog_source = "live"
            self._last_sync = time.time()
            if self._registry_ref is not None:
                self._registry_ref._chat_models.update(self.models)
            return len(self.models)
        except Exception as exc:
            self._catalog_source = "fallback" if not self.models else self._catalog_source
            log.warning("tryingopen 模型目录刷新失败，保留旧目录: %s", exc)
            return len(self.models)

    def catalog_stats(self) -> dict[str, Any]:
        return {"source": self._catalog_source, "count": len(self.models), "last_sync": self._last_sync}

    async def _sync_loop(self) -> None:
        while True:
            await asyncio.sleep(config.IF_TRYINGOPEN_SYNC_MINUTES * 60)
            await self.refresh_models()

    async def startup(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(proxy=config.PROXY, timeout=_HTTP_TIMEOUT)
        if self._sync_task is None or self._sync_task.done():
            self._sync_task = asyncio.create_task(self._sync_loop())

    async def shutdown(self) -> None:
        if self._sync_task is not None:
            self._sync_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._sync_task
            self._sync_task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None


__all__ = [
    "TryingopenChatProvider",
    "_FALLBACK_CATALOG",
    "_AttemptResult",
    "_TryingopenRateLimited",
    "_last_json_object",
    "_parse_plaintext_tool_calls",
    "DEFAULT_BASE_URL",
    "OPEN_PATH",
    "DEFAULT_EFFORT",
    "_HTTP_TIMEOUT",
    "_CHUNK_RE",
    "_MODEL_RE",
    "_resolve",
    "_parse_context_window",
    "_media_type",
    "_content_text",
    "_message_parts",
    "_tool_instruction",
    "_tool_candidate",
    "_looks_like_tool_call",
]
