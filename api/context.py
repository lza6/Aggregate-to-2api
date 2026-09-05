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
request_context_var: contextvars.ContextVar[RequestContext | None] = contextvars.ContextVar(
    "request_context", default=None
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
    blocked:     是否被安全风控拦截（被封 IP 再请求时置 True，access log 不记入 log_buffer）
    """

    request_id: str
    trace_id: str | None
    client_ip: str
    model: str
    start_time: float
    blocked: bool = False

    def effective_trace_id(self) -> str:
        """全链路统一 traceId：上游传入优先，否则回退 request_id（保证永不为空）。"""
        return self.trace_id or self.request_id


# ── Public API ────────────────────────────────────────────
def get_current_context() -> RequestContext | None:
    """获取当前请求的上下文。无活跃请求时返回 None。"""
    return request_context_var.get()


def get_current_trace_id() -> str | None:
    """获取当前请求的全链路 traceId（无活跃请求时返回 None）。

    供 worker/dispatch/audit/slow_log 在已进入请求上下文的协程内取统一 id，
    无需 OTel 启用——B2 要求入口请求日志/审计/慢日志全程 grep 同一 id。
    """
    ctx = request_context_var.get()
    return ctx.effective_trace_id() if ctx is not None else None


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
            # 包装 send 以注入 X-Request-ID / X-Trace-ID 响应头（P3-2 链路级 TraceId 透传）
            async def send_with_request_id(message):
                if message["type"] == "http.response.start":
                    status = message.get("status", 200)
                    headers = list(message.get("headers", []))
                    existing = {k.lower() for k, _ in headers}
                    headers.append((b"X-Request-ID", ctx.request_id.encode()))
                    # X-Trace-ID：透传入口 trace_id（若上游传 X-Trace-ID 则回声，否则回退 request_id）
                    if b"x-trace-id" not in existing:
                        trace_val = ctx.effective_trace_id()
                        headers.append((b"X-Trace-ID", trace_val.encode()))
                    message["headers"] = headers
                    dur = round((time.time() - ctx.start_time) * 1000, 1)
                    path = scope.get("path", "")
                    method = scope.get("method", "")
                    # 仅写入内存 log_buffer，绝不调用 uvicorn.access logger：
                    # uvicorn 的 AccessFormatter.formatMessage 会按固定模板解包 record.args（3 个值），
                    # 用 () 构造的 record 触发 "not enough values to unpack (expected 5, got 0)" 日志噪声。
                    # v7.7.20: 被安全风控拦截的请求（blocked=True）不记 access log，
                    # 避免被封 IP 刷请求淹没日志（用户诉求：拉黑的 IP 再请求不出现在日志）。
                    if path != "/v1/logs" and not path.startswith("/static") and not ctx.blocked:
                        try:
                            from .log_buffer import log_buffer

                            # P3-6: 日志脱敏——query string 中 ?api_key=xxx 泄露完整 Key，
                            # 落入 log_buffer 历史即泄露。这里仅记录 path（不含 query），
                            # 如需调试可单独显式开启，默认不把 query 写入访问日志。
                            log_msg = f'{client_host} - "{method} {path} HTTP/1.1" {status} ({dur}ms)'
                            record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, log_msg, (), None)
                            log_buffer.emit(record)
                        except Exception:
                            pass
                await send(message)

            await self.app(scope, receive, send_with_request_id)
        finally:
            request_context_var.reset(token)


# ── LogRecord Filter ──────────────────────────────────────
class RequestIdLogFilter(logging.Filter):
    """向日志消息追加全链路 traceId 片段。

    B2: 统一为 [trace=<trace_id>]（入口请求的 trace_id 或回退 request_id），
    使一次生成请求的日志/审计/慢日志 grep 同一 id 串联。无活跃请求时不追加。
    与 OTel 的 TraceIdLogFilter 共存，追加在 OTel trace 后缀之后。

    向后兼容：保留 [req=...] 旧格式的同时加 [trace=...]，旧日志查看器不坏。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = get_current_context()
        if ctx is not None:
            tid = ctx.effective_trace_id()
            if tid:
                record.msg = f"{record.msg} [req={ctx.request_id}] [trace={tid}]"
        return True
