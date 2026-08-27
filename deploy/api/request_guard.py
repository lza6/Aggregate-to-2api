"""公开生成接口的轻量请求限速。

仅按客户端 IP 限制突发刷量，保护上游 Turnstile 求解额度与号池；
不做提示词内容过滤（内容策略由各上游负责）。

v4.4.2 防刷补强：
- per-IP 窗口从纯内存升级为「内存滑窗 + 计数条数阈值拦截」；
- 识别真实客户端 IP：优先 X-Forwarded-For 首段（Nginx/Caddy 反代），
  缺省回退 request.client.host，避免反代后所有流量都算成 127.0.0.1 而失效。
"""
from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import Request

from . import config
from .errors import AppError, ErrorCodes

_lock = threading.Lock()
_requests: dict[str, deque[float]] = {}
_WINDOW_SECONDS = 60.0
_DEFAULT_REQUESTS_PER_MINUTE = 10


def _limit() -> int:
    """每分钟每 IP 允许的提交次数；0 表示关闭限速。"""
    return int(getattr(config, "IF_REQUESTS_PER_MINUTE", 0) or 0)


def _client_ip(request: Request) -> str:
    """在反代之后仍能拿到真实客户端 IP。"""
    # 优先级：X-Forwarded-For 最左边的非空、非 known-proxy 段
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        first = xff.split(",", 1)[0].strip()
        if first and not first.lower().startswith(("127.", "10.", "192.168.", "::1", "unknown")):
            return first
    client = request.client
    return client.host if client else "unknown"


def check_rate_limit(request: Request) -> None:
    """滑动窗口 per-IP 限速；窗口过期记录自动清理。"""
    limit = _limit()
    if limit <= 0:
        return
    key = _client_ip(request)
    now = time.monotonic()
    with _lock:
        bucket = _requests.setdefault(key, deque())
        while bucket and now - bucket[0] >= _WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= limit:
            raise AppError(ErrorCodes.RATE_LIMITED,
                           f"请求过于频繁（>{limit}/分钟），请稍后重试", 429)
        bucket.append(now)
        # 防止长期运行时 key 无限增长。
        if len(_requests) > 10000:
            expired = [k for k, values in _requests.items()
                       if not values or now - values[-1] >= _WINDOW_SECONDS]
            for k in expired:
                _requests.pop(k, None)


def check_generate_request(request: Request, prompt: str = "") -> None:
    """入口限速；prompt 参数保留以兼容调用方，不做内容过滤。"""
    del prompt
    check_rate_limit(request)
