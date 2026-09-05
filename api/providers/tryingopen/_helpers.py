"""tryingopen 提供商的纯辅助函数、常量、dataclass 与异常。

从原 `api/providers/tryingopen.py`（810 行）拆出（P0-6）。
这些符号不依赖运行时 monkeypatch 命中点（``proxy_pool``/``asyncio``/``config``
仍绑定在包 ``__init__`` 顶层，``TryingopenChatProvider`` 方法内经模块 globals
解析才能被 tests/test_tryingopen.py 的 monkeypatch 命中），故可安全下沉。
"""

from __future__ import annotations

import inspect
import json
import mimetypes
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

DEFAULT_BASE_URL = "https://www.tryingopen.com"
OPEN_PATH = "/api/open"
DEFAULT_EFFORT = "balanced"
_HTTP_TIMEOUT = (10, 120)
_CHUNK_RE = re.compile(r"/_next/static/chunks/[A-Za-z0-9._~-]+\.js")
_MODEL_RE = re.compile(r'\{id:"([a-z0-9][a-z0-9.\-]*/[a-z0-9][a-z0-9.\-]*)",' r'name:"([^"]+)"')


# 站点目录不可访问时仍需提供可用的静态目录。
_FALLBACK_CATALOG: tuple[dict[str, Any], ...] = (
    # P0-3：演示性 meta.system_prompt_template 配置——按模型家族挂不同人格模板
    # 用户可通过 refresh_models 动态目录覆盖；无 system_prompt_template 键走原 [SYSTEM INSTRUCTIONS] 路径
    {"id": "z-ai/glm-5.3-flash", "name": "GLM-5.3 Flash", "context": "128k", "supportsTools": True,
     "system_prompt_template": "kimi_k2_teach", "thinking_mode": "interleaved", "refusal_stance": "default_help"},
    {"id": "z-ai/glm-5.2", "name": "GLM-5.2", "context": "128k", "supportsTools": True,
     "system_prompt_template": "kimi_k2_teach", "thinking_mode": "interleaved"},
    {"id": "qwen/qwen3.8-27b", "name": "Qwen3.8 27B", "context": "128k", "supportsTools": True,
     "system_prompt_template": "kimi_k2_teach"},
    {"id": "nvidia/nemotron-3.5-lightning", "name": "Nemotron 3.5 Lightning", "context": "128k"},
    {"id": "deepseek/deepseek-v4-flash-0731", "name": "DeepSeek V4 Flash", "context": "128k", "supportsTools": True,
     "system_prompt_template": "anthropic_v5_chat", "thinking_mode": "interleaved"},
    {"id": "deepseek/deepseek-v4-pro-0813", "name": "DeepSeek V4 Pro", "context": "128k", "supportsTools": True,
     "system_prompt_template": "anthropic_v5_chat", "thinking_mode": "interleaved", "max_thinking_length": 12000},
    {"id": "google/gemma-4-31b-it", "name": "Gemma 4 31B IT", "context": "128k"},
    {"id": "google/gemma-4-26b-a4b-it", "name": "Gemma 4 26B A4B IT", "context": "128k"},
    {"id": "openai/gpt-oss-120b", "name": "GPT OSS 120B", "context": "128k", "supportsTools": True,
     "system_prompt_template": "anthropic_v5_chat"},
    {"id": "meta/muse-glimmer-30b", "name": "Muse Glimmer 30B", "context": "128k"},
    {
        "id": "moonshotai/kimi-k3",
        "name": "Kimi K3",
        "context": "256k",
        "supportsTools": True,
        "messageLimit": 5,
        "cheaperFallbackId": "minimax/minimax-m3",
        "system_prompt_template": "kimi_k2_teach",
        "thinking_mode": "interleaved",
        "max_thinking_length": 16000,
    },
    {"id": "minimax/minimax-m3", "name": "MiniMax M3", "context": "128k", "supportsTools": True,
     "system_prompt_template": "kimi_k2_teach"},
    {"id": "thinkingmachines/inkling-small", "name": "Inkling Small", "context": "64k"},
)


@dataclass
class _AttemptResult:
    reasoning: str = ""
    text: str = ""
    usage: dict[str, int] | None = None
    finish_reason: str = "stop"


class _TryingopenRateLimited(Exception):
    """单次 tryingopen 请求被限流，交给外层切换出口。"""

    def __init__(self, message: str = "tryingopen 请求被限流") -> None:
        super().__init__(message)
        self.message = message


async def _resolve(value: Any) -> Any:
    """兼容真实异步实现与测试替身。"""
    return await value if inspect.isawaitable(value) else value


def _parse_context_window(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace(" ", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(k|m)?", text)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    if unit == "k":
        number *= 1024
    elif unit == "m":
        number *= 1024 * 1024
    return int(number)


def _media_type(url: str) -> str:
    if url.startswith("data:"):
        header = url[5:].split(",", 1)[0]
        media = header.split(";", 1)[0].strip()
        if media:
            return media
    suffix = urlparse(url).path.rsplit(".", 1)[-1].lower() if "." in urlparse(url).path else ""
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
        "avif": "image/avif",
    }.get(suffix, mimetypes.guess_type(url)[0] or "application/octet-stream")


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    if isinstance(content, list):
        return "".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content)


def _message_parts(content: Any) -> list[dict[str, str]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if content is None:
        return []
    if not isinstance(content, list):
        return [{"type": "text", "text": str(content)}]
    parts: list[dict[str, str]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "text":
            parts.append({"type": "text", "text": str(item.get("text", ""))})
        elif item_type == "image_url":
            image = item.get("image_url")
            url = image.get("url") if isinstance(image, dict) else image
            if isinstance(url, str) and url:
                parts.append({"type": "file", "mediaType": _media_type(url), "url": url})
    return parts


def _tool_instruction(tools: list[Any], tool_choice: Any) -> str:
    serialized = json.dumps(tools, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    instruction = (
        "[TOOL CALLING MODE]\n"
        f"Available tools (JSON): {serialized}\n"
        "If you need to call a tool, respond with ONLY a single JSON object and no other text, "
        'no markdown fences: {"tool_call":{"name":"<exact tool name>","arguments":{...}}}\n'
        "If no tool call is needed, answer normally as plain text."
    )
    if isinstance(tool_choice, dict):
        name = (tool_choice.get("function") or {}).get("name")
        if isinstance(name, str) and name:
            instruction += f'\nYou MUST call the tool named "{name}".'
    elif tool_choice == "required":
        instruction += "\nYou MUST call one or more tools."
    return instruction


def _tool_candidate(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if isinstance(value.get("tool_call"), dict):
        return True
    for key in ("tool", "tool_name"):
        nested = value.get(key)
        if isinstance(nested, dict) and isinstance(nested.get("name"), str):
            return True
    return isinstance(value.get("name") or value.get("tool") or value.get("tool_name"), str) and any(
        key in value for key in ("arguments", "args", "parameters")
    )


def _looks_like_tool_call(value: Any) -> bool:
    values = value if isinstance(value, list) else [value]
    return any(_tool_candidate(item) for item in values)


def _last_json_object(text: str) -> tuple[Any | None, int | None]:
    """从文本中选择最后一个合法且像工具调用的 JSON 对象。"""
    if not text:
        return None, None
    normalized = text
    decoder = json.JSONDecoder()
    last_valid: tuple[Any, int] | None = None
    tool_candidates: list[tuple[int, int, Any]] = []
    for match in re.finditer(r"[\{\[]", normalized):
        try:
            value, end = decoder.raw_decode(normalized, match.start())
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(value, (dict, list)):
            last_valid = (value, match.start())
            if _looks_like_tool_call(value):
                tool_candidates.append((match.start(), end, value))
    if tool_candidates:
        outer_candidates = [
            candidate
            for candidate in tool_candidates
            if not any(other[0] < candidate[0] and candidate[1] <= other[1] for other in tool_candidates)
        ]
        start, end, value = max(outer_candidates, key=lambda item: item[0])
        return value, start
    return last_valid or (None, None)


def _parse_plaintext_tool_calls(text: str) -> list[dict[str, str]] | None:
    found, _ = _last_json_object(text)
    if found is None:
        return None
    items = found if isinstance(found, list) else [found]
    calls: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        inner = item
        if isinstance(inner.get("tool_call"), dict):
            inner = inner["tool_call"]
        elif isinstance(inner.get("tool"), dict):
            inner = inner["tool"]
        name = inner.get("name") or inner.get("tool") or inner.get("tool_name")
        arguments = inner.get("arguments")
        if arguments is None:
            arguments = inner.get("args")
        if arguments is None:
            arguments = inner.get("parameters")
        if not isinstance(name, str) or not name:
            continue
        if isinstance(arguments, (dict, list)):
            arguments = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
        if not isinstance(arguments, str):
            arguments = "{}"
        calls.append({"name": name, "arguments": arguments})
    return calls or None


__all__ = [
    "DEFAULT_BASE_URL",
    "OPEN_PATH",
    "DEFAULT_EFFORT",
    "_HTTP_TIMEOUT",
    "_CHUNK_RE",
    "_MODEL_RE",
    "_FALLBACK_CATALOG",
    "_AttemptResult",
    "_TryingopenRateLimited",
    "_resolve",
    "_parse_context_window",
    "_media_type",
    "_content_text",
    "_message_parts",
    "_tool_instruction",
    "_tool_candidate",
    "_looks_like_tool_call",
    "_last_json_object",
    "_parse_plaintext_tool_calls",
]
