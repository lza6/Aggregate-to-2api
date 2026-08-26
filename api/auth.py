"""v4.4: 全局 API Key 鉴权（防滥用）。

设计：
- 固定静态 Key 池由环境变量 IF_API_KEYS 注入（逗号分隔）；空 = 开放模式。
- 支持三种传递方式（按优先级）：Authorization: Bearer <key> / X-API-Key: <key> / ?api_key=<key>。
- 图像主链路默认开放（公益站定位不变）；聊天端点强制走 check_api_key()。
- 管理面 /admin/* 与 healthz/metrics 等运维端点不走此鉴权（有独立的画廊密码/DLQ 权限模型）。
"""
from __future__ import annotations

import hmac
import logging
import threading
import time
from collections import deque

from fastapi import Request

from . import config
from .errors import AppError, ErrorCodes

log = logging.getLogger("imagefree_api.auth")

_lock = threading.Lock()
_chat_buckets: dict[str, deque[float]] = {}
_WINDOW_SECONDS = 60.0


def _keys() -> list[str]:
    """当前生效 Key 列表（环境热更新友好，每次现读）。"""
    return [k.strip() for k in (config.settings.api_keys or []) if k and k.strip()]


def auth_enabled() -> bool:
    """是否启用鉴权：只要配置了至少一个 Key 即开启。"""
    return bool(_keys())


def _extract_key(request: Request) -> str:
    auth_header = request.headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    header_key = request.headers.get("x-api-key") or ""
    if header_key:
        return header_key.strip()
    return (request.query_params.get("api_key") or "").strip()


def check_api_key(request: Request, *, scope: str = "chat") -> None:
    """校验请求携带的 API Key。未启用时直接放行（零破坏）。"""
    keys = _keys()
    if not keys:
        return
    provided = _extract_key(request)
    if not provided:
        raise AppError(
            ErrorCodes.UNAUTHORIZED,
            f"缺少 API Key：请在 Authorization: Bearer <key> / X-API-Key 头或 ?api_key= 参数中提供",
            401,
            details={"scope": scope},
        )
    # 常数时间比较防时序侧信道；任一 Key 匹配即通过
    ok = any(hmac.compare_digest(provided, k) for k in keys)
    if not ok:
        raise AppError(ErrorCodes.UNAUTHORIZED, "API Key 无效或已撤销", 401,
                       details={"scope": scope})


def check_chat_rate_limit(request: Request) -> None:
    """聊天端点每客户端限流（独立于生图 request_guard 的窗口）。"""
    limit = int(getattr(config.settings, "chat_requests_per_minute", 60))
    if limit <= 0:
        return
    client = request.client
    key = client.host if client else "unknown"
    now = time.monotonic()
    with _lock:
        bucket = _chat_buckets.setdefault(key, deque())
        while bucket and now - bucket[0] >= _WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= limit:
            raise AppError(ErrorCodes.RATE_LIMITED, "聊天请求过于频繁，请稍后重试", 429)
        bucket.append(now)
        if len(_chat_buckets) > 10000:
            expired = [k for k, v in _chat_buckets.items()
                       if not v or now - v[-1] >= _WINDOW_SECONDS]
            for k in expired:
                _chat_buckets.pop(k, None)


def guard_chat_request(request: Request) -> None:
    """聊天端点组合守卫：Key 校验 + 频控。"""
    check_api_key(request, scope="chat")
    check_chat_rate_limit(request)
