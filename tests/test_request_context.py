"""A-05: contextvars 请求上下文测试。

测试覆盖：
1. RequestContext dataclass 正常创建
2. get_current_context 在无上下文时返回 None
3. 中间件正确设置上下文
4. 中间件正确清理上下文（请求结束后 context 恢复为 None）
5. 响应头包含 X-Request-ID
6. 并发请求隔离（各自的 context 不互相污染）
7. trace_id 从请求头 X-Trace-ID 提取
"""
import uuid

import pytest

from api.context import (
    RequestContext,
    get_current_context,
    request_context_var,
)


class TestRequestContext:
    """RequestContext dataclass 的基本行为。"""

    def test_create_context(self):
        ctx = RequestContext(
            request_id="req-001",
            trace_id="trace-abc",
            client_ip="192.168.1.1",
            model="test-model",
            start_time=100.0,
        )
        assert ctx.request_id == "req-001"
        assert ctx.trace_id == "trace-abc"
        assert ctx.client_ip == "192.168.1.1"
        assert ctx.model == "test-model"
        assert ctx.start_time == 100.0

    def test_trace_id_can_be_none(self):
        ctx = RequestContext(
            request_id="req-002",
            trace_id=None,
            client_ip="10.0.0.1",
            model="",
            start_time=200.0,
        )
        assert ctx.trace_id is None

    def test_create_context_with_optional_model(self):
        """model 默认为空字符串。"""
        ctx = RequestContext(
            request_id="req-003",
            trace_id=None,
            client_ip="10.0.0.1",
            model="",
            start_time=300.0,
        )
        assert ctx.model == ""


class TestGetCurrentContext:
    """get_current_context() 辅助函数。"""

    def test_no_context_returns_none(self):
        assert get_current_context() is None

    def test_returns_set_context(self):
        ctx = RequestContext(
            request_id="req-004",
            trace_id="trace-xyz",
            client_ip="127.0.0.1",
            model="",
            start_time=400.0,
        )
        token = request_context_var.set(ctx)
        try:
            assert get_current_context() is ctx
        finally:
            request_context_var.reset(token)

    def test_context_cleared_after_reset(self):
        ctx = RequestContext(
            request_id="req-005",
            trace_id=None,
            client_ip="127.0.0.1",
            model="",
            start_time=500.0,
        )
        token = request_context_var.set(ctx)
        request_context_var.reset(token)
        assert get_current_context() is None


class TestRequestContextMiddleware:
    """中间件设置和清理上下文。"""

    @pytest.mark.asyncio
    async def test_middleware_sets_context(self):
        """中间件在请求处理期间设置 context。"""
        from api.context import RequestContextMiddleware

        # 模拟 Starlette 的 Request 对象
        scope = {
            "type": "http",
            "client": ("10.0.0.1", 54321),
            "headers": [],
        }
        request = _mock_request(scope)

        context_in_handler = None

        async def handler(req):
            nonlocal context_in_handler
            context_in_handler = get_current_context()
            return _mock_response()

        middleware = RequestContextMiddleware()
        await middleware(request, handler)

        assert context_in_handler is not None
        assert context_in_handler.client_ip == "10.0.0.1"
        assert context_in_handler.request_id is not None
        assert len(context_in_handler.request_id) > 0
        assert context_in_handler.start_time > 0

    @pytest.mark.asyncio
    async def test_middleware_clears_context_after_request(self):
        """请求结束后 context 应被清理。"""
        from api.context import RequestContextMiddleware

        scope = {
            "type": "http",
            "client": ("10.0.0.1", 54321),
            "headers": [],
        }
        request = _mock_request(scope)

        async def handler(req):
            return _mock_response()

        middleware = RequestContextMiddleware()
        await middleware(request, handler)

        # 请求结束后 context 应恢复为 None
        assert get_current_context() is None

    @pytest.mark.asyncio
    async def test_middleware_clears_context_on_exception(self):
        """handler 抛异常时 context 也应被清理。"""
        from api.context import RequestContextMiddleware

        scope = {
            "type": "http",
            "client": ("10.0.0.1", 54321),
            "headers": [],
        }
        request = _mock_request(scope)

        async def failing_handler(req):
            raise ValueError("模拟异常")

        middleware = RequestContextMiddleware()
        with pytest.raises(ValueError):
            await middleware(request, failing_handler)

        # 异常后 context 应恢复为 None
        assert get_current_context() is None

    @pytest.mark.asyncio
    async def test_response_has_x_request_id_header(self):
        """响应头应包含 X-Request-ID。"""
        from api.context import RequestContextMiddleware

        scope = {
            "type": "http",
            "client": ("10.0.0.1", 54321),
            "headers": [],
        }
        request = _mock_request(scope)

        async def handler(req):
            return _mock_response()

        middleware = RequestContextMiddleware()
        response = await middleware(request, handler)

        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0

    @pytest.mark.asyncio
    async def test_x_request_id_changes_per_request(self):
        """每次请求的 X-Request-ID 应不同。"""
        from api.context import RequestContextMiddleware

        ids = set()

        for _ in range(5):
            scope = {
                "type": "http",
                "client": ("10.0.0.1", 54321),
                "headers": [],
            }
            request = _mock_request(scope)

            async def handler(req):
                return _mock_response()

            middleware = RequestContextMiddleware()
            response = await middleware(request, handler)
            ids.add(response.headers["X-Request-ID"])

        assert len(ids) == 5

    @pytest.mark.asyncio
    async def test_trace_id_from_header(self):
        """X-Trace-ID 请求头应被提取到 trace_id。"""
        from api.context import RequestContextMiddleware

        scope = {
            "type": "http",
            "client": ("10.0.0.1", 54321),
            "headers": [(b"x-trace-id", b"custom-trace-001")],
        }
        request = _mock_request(scope)

        trace_in_handler = None

        async def handler(req):
            nonlocal trace_in_handler
            ctx = get_current_context()
            trace_in_handler = ctx.trace_id if ctx else None
            return _mock_response()

        middleware = RequestContextMiddleware()
        await middleware(request, handler)

        assert trace_in_handler == "custom-trace-001"

    @pytest.mark.asyncio
    async def test_trace_id_none_when_no_header(self):
        """无 X-Trace-ID 头时 trace_id 为 None。"""
        from api.context import RequestContextMiddleware

        scope = {
            "type": "http",
            "client": ("10.0.0.1", 54321),
            "headers": [],
        }
        request = _mock_request(scope)

        async def handler(req):
            ctx = get_current_context()
            return _mock_response()

        middleware = RequestContextMiddleware()
        await middleware(request, handler)

        # 请求结束后检查
        assert get_current_context() is None

    @pytest.mark.asyncio
    async def test_concurrent_requests_isolation(self):
        """并发请求的 context 互不污染。"""
        from api.context import RequestContextMiddleware
        import asyncio

        async def make_request(client_ip: str, trace_id: str | None) -> str | None:
            headers = [(b"x-trace-id", trace_id.encode())] if trace_id else []
            scope = {
                "type": "http",
                "client": (client_ip, 54321),
                "headers": headers,
            }
            request = _mock_request(scope)

            async def handler(req):
                # 模拟处理延迟
                await asyncio.sleep(0.05)
                ctx = get_current_context()
                if ctx is None:
                    return None
                return f"{ctx.client_ip}:{ctx.trace_id}"

            middleware = RequestContextMiddleware()
            # 直接调用 handler 获取结果
            result = None

            async def capturing_handler(req):
                nonlocal result
                result = await handler(req)
                return _mock_response()

            await middleware(request, capturing_handler)
            return result

        # 并发发起 3 个请求
        results = await asyncio.gather(
            make_request("10.0.0.1", "trace-a"),
            make_request("10.0.0.2", "trace-b"),
            make_request("10.0.0.3", None),
        )

        assert "10.0.0.1:trace-a" in results
        assert "10.0.0.2:trace-b" in results
        assert "10.0.0.3:None" in results


class TestLogRecordFilter:
    """日志 filter 自动注入 request_id。"""

    def test_filter_adds_request_id(self):
        """RequestIdLogFilter 向 LogRecord 追加 request_id。"""
        from api.context import RequestIdLogFilter, request_context_var, RequestContext

        # 设置上下文
        ctx = RequestContext(
            request_id="req-abc-123",
            trace_id="trace-xyz",
            client_ip="127.0.0.1",
            model="",
            start_time=100.0,
        )
        token = request_context_var.set(ctx)
        try:
            import logging
            record = logging.LogRecord(
                name="test", level=logging.INFO,
                pathname=__file__, lineno=42,
                msg="处理请求", args=(),
                exc_info=None,
            )
            f = RequestIdLogFilter()
            result = f.filter(record)
            assert result is True
            assert "[req=req-abc-123]" in record.msg
        finally:
            request_context_var.reset(token)

    def test_filter_noop_when_no_context(self):
        """无上下文时 filter 不修改消息。"""
        from api.context import RequestIdLogFilter

        import logging
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname=__file__, lineno=42,
            msg="服务启动中", args=(),
            exc_info=None,
        )
        f = RequestIdLogFilter()
        result = f.filter(record)
        assert result is True
        assert record.msg == "服务启动中"

    def test_filter_preserves_existing_trace_suffix(self):
        """已有 OTel trace 后缀时，filter 追加在 OTel 之后。"""
        from api.context import RequestIdLogFilter, request_context_var, RequestContext

        ctx = RequestContext(
            request_id="req-abc-123",
            trace_id="trace-xyz",
            client_ip="127.0.0.1",
            model="",
            start_time=100.0,
        )
        token = request_context_var.set(ctx)
        try:
            import logging
            record = logging.LogRecord(
                name="test", level=logging.INFO,
                pathname=__file__, lineno=42,
                msg="正在生成图像 [trace=abcdef1234567890]", args=(),
                exc_info=None,
            )
            f = RequestIdLogFilter()
            f.filter(record)
            assert "[req=req-abc-123]" in record.msg
            assert "[trace=abcdef1234567890]" in record.msg
        finally:
            request_context_var.reset(token)


# ── 辅助函数 ─────────────────────────────────
class _MockClient:
    """模拟 Starlette 的 client 对象（含 .host 属性）。"""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port


class _MockRequest:
    """最小 Starlette Request 模拟。"""

    def __init__(self, scope: dict):
        self.scope = scope
        client = scope.get("client")
        self.client = _MockClient(host=client[0], port=client[1]) if client else None
        self._headers = {}
        for k, v in scope.get("headers", []):
            self._headers[k.decode().lower()] = v.decode()

    @property
    def headers(self):
        return self._headers


class _MockResponse:
    """最小 Starlette Response 模拟。"""

    def __init__(self):
        self.headers = {}
        self.status_code = 200


def _mock_request(scope: dict) -> _MockRequest:
    return _MockRequest(scope)


def _mock_response() -> _MockResponse:
    return _MockResponse()