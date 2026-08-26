"""公开生成接口的轻量请求限速。

仅限制突发刷请求，不检查或修改用户提示词；内容策略仍由各上游负责。
默认不记录完整 prompt，避免敏感内容进入日志。
"""
from __future__ import annotations

import re
import threading
import time
from collections import deque

from fastapi import Request

from . import config
from .errors import AppError, ErrorCodes

# 明显违规模式：仅处理高置信度信号，避免误伤普通创作提示词。
_BLOCKED_PROMPT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("minor_sexual", re.compile(r"未成年|未满18|儿童色情|幼女|underage|minor.*sex", re.I)),
    ("sexual_nudity", re.compile(r"全裸|裸体|裸身|乳头|色情|porn|nude|naked", re.I)),
    ("graphic_violence", re.compile(r"斩首|肢解|虐杀|血腥细节|dismember|beheading|gore", re.I)),
    ("self_harm", re.compile(r"自杀方法|自残方法|suicide method|how to self.harm", re.I)),
)

_lock = threading.Lock()
_requests: dict[str, deque[float]] = {}
_WINDOW_SECONDS = 60.0
_DEFAULT_REQUESTS_PER_MINUTE = 30


def prompt_risk_category(prompt: str) -> str | None:
    """返回明显风险类别；普通提示词返回 None。"""
    text = (prompt or "").strip()
    for category, pattern in _BLOCKED_PROMPT_PATTERNS:
        if pattern.search(text):
            return category
    return None


def check_prompt(prompt: str) -> None:
    """拦截高置信度违规提示词，不把原始 prompt 写入异常消息。"""
    category = prompt_risk_category(prompt)
    if category:
        raise AppError(
            ErrorCodes.INVALID_PROMPT,
            f"提示词未通过内容安全检查（类别: {category}）",
            422,
        )


def check_rate_limit(request: Request) -> None:
    """按客户端地址限制提交频率，窗口过期记录自动清理。"""
    limit = int(getattr(config, "IF_REQUESTS_PER_MINUTE", _DEFAULT_REQUESTS_PER_MINUTE))
    if limit <= 0:
        return
    client = request.client
    key = client.host if client else "unknown"
    now = time.monotonic()
    with _lock:
        bucket = _requests.setdefault(key, deque())
        while bucket and now - bucket[0] >= _WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= limit:
            raise AppError(ErrorCodes.RATE_LIMITED, "请求过于频繁，请稍后重试", 429)
        bucket.append(now)
        # 防止长期运行时 key 无限增长。
        if len(_requests) > 10000:
            expired = [k for k, values in _requests.items() if not values or now - values[-1] >= _WINDOW_SECONDS]
            for expired_key in expired:
                _requests.pop(expired_key, None)


def check_generate_request(request: Request, prompt: str) -> None:
    """执行入口限速；prompt 参数保留以兼容调用方，不做内容过滤。"""
    del prompt
    check_rate_limit(request)
