"""A-05: contextvars 请求上下文。

提供统一的请求上下文管理，用 contextvars 替代函数参数透传 trace_id、request_id 等。
后续 A-01/A-03 可逐步迁移使用此上下文。
"""
from __future__ import annotations

import contextvars
import logging
import time
import uuid
from dataclasses import dataclass

# ── ContextVar ─────────────────────────────────────────────
request_context_var: contextvars.ContextVar[Optional["RequestContext"]] = (
    contextvars.ContextVar("request_context", default=None)
)


# ── Data Classes ──────────────────────────────────────────
@dataclass
class RequestContext:
    """单个 HTTP 请求的上下文信息。

    request_id:  请求唯一标识（UUID），注入响应头 X-Request-ID
    trace_id:    上游追踪 ID（从 X-Trace-ID 请求头提取），用于日志关联
    client_ip:   客户端 IP
    model:       请求使用的模型名称（由路由处理程序填充）
    start_time:  请求到达时间戳（time.time()）
    """

    request_id: str
    trace_id: str | None
    client_ip: str
    model: str
    start_time: float


# ── Public API ────────────────────────────────────────────
def get_current_context() -> Optional[RequestContext]:
    """获取当前请求的上下文。无活跃请求时返回 None。"""
    return request_context_var.get()


def extract_trace_id(request_headers: dict) -> str | None:
    """从请求头提取 trace_id。

    优先使用 X-Trace-ID，其次 X-Request-ID，均不存在时返回 None。
    """
    for key in ("x-trace-id", "x-request-id"):
        val = request_headers.get(key)
        if val:
            return val
    return None


# ── Middleware ─────────────────────────────────────────────
class RequestContextMiddleware:
    """FastAPI/Starlette ASGI middleware：在每个请求开始时设置 context，结束时清理。

    用法：
        app.add_middleware(RequestContextMiddleware)

    注意：此类作为 ASGI middleware 使用，__call__ 接收 (scope, receive, send) 三元组。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 提取客户端 IP
        client_host = "unknown"
        try:
            client_info = scope.get("client")
            if client_info:
                client_host = client_info[0]
        except Exception:
            pass

        # 提取请求头
        headers = {}
        try:
            for key, value in scope.get("headers", []):
                headers[key.decode("latin-1").lower()] = value.decode("latin-1")
        except Exception:
            pass

        # 创建上下文
        ctx = RequestContext(
            request_id=str(uuid.uuid4()),
            trace_id=extract_trace_id(headers),
            client_ip=client_host,
            model="",
            start_time=time.time(),
        )
        token = request_context_var.set(ctx)
        try:
            # 包装 send 以注入 X-Request-ID 响应头
            async def send_with_request_id(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"X-Request-ID", ctx.request_id.encode()))
                    message["headers"] = headers
                await send(message)

            await self.app(scope, receive, send_with_request_id)
        finally:
            request_context_var.reset(token)


# ── LogRecord Filter ──────────────────────────────────────
class RequestIdLogFilter(logging.Filter):
    """向日志消息追加 request_id 片段。

    效果：每条日志末尾追加 [req=<request_id>]，无活跃请求时不追加。
    与 OTel 的 TraceIdLogFilter 共存，追加在 OTel trace 后缀之后。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = get_current_context()
        if ctx is not None and ctx.request_id:
            record.msg = f"{record.msg} [req={ctx.request_id}]"
        return True