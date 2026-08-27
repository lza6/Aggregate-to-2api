"""v4.4: 全局 API Key 鉴权（防滥用）。

设计：
- 固定静态 Key 池由环境变量 IF_API_KEYS 注入（逗号分隔）；空 = 开放模式。
- 支持三种传递方式（按优先级）：Authorization: Bearer <key> / X-API-Key: <key> / ?api_key=<key>。
- v4.4.2：全站写操作（生图 /v1/generate*、图生图 /v1/edit、聊天 /v1/chat/*、/v1/messages）统一强制 Key。
- 只读端点（/v1/stats、/v1/providers、/v1/models、/v1/meta、/v1/healthz 等）与运维端点保持公开/独立权限。
- public_keymask() 用于 UI 展示脱敏前缀（不泄露完整 Key）。
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
    raw = getattr(config.settings, "if_api_keys", "") or ""
    if isinstance(raw, list):
        return [k.strip() for k in raw if k and k.strip()]
    return [k.strip() for k in str(raw).split(",") if k.strip()]


def auth_enabled() -> bool:
    """是否启用鉴权：只要配置了至少一个 Key 即开启。"""
    return bool(_keys())


def public_keymask() -> str:
    """返回脱敏后的 Key 展示（如 sk-tfai-7f77***）。供 UI 实时显示，不泄露完整 Key。"""
    keys = _keys()
    if not keys:
        return ""
    first = keys[0]
    return first[:12] + "***" if len(first) > 12 else first + "***"


def first_key() -> str:
    """返回当前生效首把完整 Key（供站长管理面板一键复制的接口/内置前端使用）。

    注意：此接口会把 Key 返回给调用者本身。仅用于可信管理面（/admin UI 是
    区分调用者的自取场景）；对公网匿名扫接口会在 auth/status 中被严格鉴权。
    """
    keys = _keys()
    return keys[0] if keys else ""


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


def guard_generate_request(request: Request) -> None:
    """生图/图生图端点守卫：与聊天端点一致要求 Key（未配置时开放）。"""
    check_api_key(request, scope="generate")
    # 把真实客户端 IP 挂到请求 state，供 dispatch 落库记录调用者（防刷取证）
    request.state.client_ip = _client_ip_of(request)


def _client_ip_of(request: Request) -> str:
    """提取真实客户端 IP（优先 X-Forwarded-For 首段，回退 socket）。"""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        first = xff.split(",", 1)[0].strip()
        if first and not first.lower().startswith(("127.", "10.", "192.168.", "::1", "unknown")):
            return first
    return (request.client.host if request.client else "unknown")
