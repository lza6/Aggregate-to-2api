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

        scope = {
            "type": "http",
            "client": ("10.0.0.1", 54321),
            "headers": [],
        }
        context_in_handler = None

        async def app(scope, receive, send):
            nonlocal context_in_handler
            context_in_handler = get_current_context()
            # send dummy response
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"",
                }
            )

        middleware = RequestContextMiddleware(app)
        await middleware(scope, _mock_receive, _mock_send)

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

        async def app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"",
                }
            )

        middleware = RequestContextMiddleware(app)
        await middleware(scope, _mock_receive, _mock_send)

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

        async def failing_app(scope, receive, send):
            raise ValueError("模拟异常")

        middleware = RequestContextMiddleware(failing_app)
        with pytest.raises(ValueError):
            await middleware(scope, _mock_receive, _mock_send)

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
        captured_headers = []

        async def send_capture(message):
            if message["type"] == "http.response.start":
                captured_headers.extend(message.get("headers", []))
            await _mock_send(message)

        async def app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"",
                }
            )

        middleware = RequestContextMiddleware(app)
        await middleware(scope, _mock_receive, send_capture)

        # Response headers should contain X-Request-ID
        header_keys = [k.decode().lower() for k, v in captured_headers]
        assert "x-request-id" in header_keys

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
            captured_headers = []

            async def send_capture(message):
                if message["type"] == "http.response.start":
                    captured_headers.extend(message.get("headers", []))
                await _mock_send(message)

            async def app(scope, receive, send):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"",
                    }
                )

            middleware = RequestContextMiddleware(app)
            await middleware(scope, _mock_receive, send_capture)

            for k, v in captured_headers:
                if k.decode().lower() == "x-request-id":
                    ids.add(v.decode())

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
        trace_in_handler = None

        async def app(scope, receive, send):
            nonlocal trace_in_handler
            ctx = get_current_context()
            trace_in_handler = ctx.trace_id if ctx else None
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"",
                }
            )

        middleware = RequestContextMiddleware(app)
        await middleware(scope, _mock_receive, _mock_send)

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
        trace_in_handler = None

        async def app(scope, receive, send):
            nonlocal trace_in_handler
            ctx = get_current_context()
            trace_in_handler = ctx.trace_id if ctx else None
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"",
                }
            )

        middleware = RequestContextMiddleware(app)
        await middleware(scope, _mock_receive, _mock_send)

        assert trace_in_handler is None

    @pytest.mark.asyncio
    async def test_response_x_trace_id_echoes_inbound_header(self):
        """P3-2: 入站带 X-Trace-ID → 响应回声同一 trace_id（链路透传）。"""
        from api.context import RequestContextMiddleware

        scope = {
            "type": "http",
            "client": ("10.0.0.1", 54321),
            "headers": [(b"x-trace-id", b"inbound-trace-xyz")],
        }
        captured: list[tuple[bytes, bytes]] = []

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        async def send(message):
            if message["type"] == "http.response.start":
                captured.extend(message.get("headers", []))

        middleware = RequestContextMiddleware(app)
        await middleware(scope, _mock_receive, send)

        header_map = {k.decode().lower(): v.decode() for k, v in captured}
        assert header_map["x-trace-id"] == "inbound-trace-xyz"
        assert "x-request-id" in header_map

    @pytest.mark.asyncio
    async def test_response_x_trace_id_falls_back_to_request_id(self):
        """P3-2: 入站无 X-Trace-ID → 响应回退 request_id 作为 X-Trace-ID。"""
        from api.context import RequestContextMiddleware

        scope = {"type": "http", "client": ("10.0.0.1", 1), "headers": []}
        captured: list[tuple[bytes, bytes]] = []

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        async def send(message):
            if message["type"] == "http.response.start":
                captured.extend(message.get("headers", []))

        middleware = RequestContextMiddleware(app)
        await middleware(scope, _mock_receive, send)

        header_map = {k.decode().lower(): v.decode() for k, v in captured}
        # X-Trace-ID 回退 = X-Request-ID（两者都由中间件注入，trace 回退 request_id）
        assert header_map["x-trace-id"] == header_map["x-request-id"]
        assert header_map["x-trace-id"]

    @pytest.mark.asyncio
    async def test_response_x_trace_id_not_duplicated_if_already_present(self):
        """P3-2: 下游已设 X-Trace-ID 响应头 → 中间件不重复注入。"""
        from api.context import RequestContextMiddleware

        scope = {
            "type": "http",
            "client": ("10.0.0.1", 1),
            "headers": [(b"x-trace-id", b"upstream-trace")],
        }
        captured: list[tuple[bytes, bytes]] = []

        async def app(scope, receive, send):
            # 下游已自己写了 X-Trace-ID 响应头
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"X-Trace-ID", b"downstream-set")]})
            await send({"type": "http.response.body", "body": b""})

        async def send(message):
            if message["type"] == "http.response.start":
                captured.extend(message.get("headers", []))

        middleware = RequestContextMiddleware(app)
        await middleware(scope, _mock_receive, send)

        trace_vals = [v.decode() for k, v in captured if k.decode().lower() == "x-trace-id"]
        assert trace_vals == ["downstream-set"]  # 不被覆盖、不重复

    @pytest.mark.asyncio
    async def test_concurrent_requests_isolation(self):
        """并发请求的 context 互不污染。"""
        import asyncio

        from api.context import RequestContextMiddleware

        async def make_request(client_ip: str, trace_id: str | None) -> str | None:
            headers = [(b"x-trace-id", trace_id.encode())] if trace_id else []
            scope = {
                "type": "http",
                "client": (client_ip, 54321),
                "headers": headers,
            }

            result = None

            async def app(scope, receive, send):
                nonlocal result
                await asyncio.sleep(0.05)
                ctx = get_current_context()
                if ctx is None:
                    result = None
                else:
                    result = f"{ctx.client_ip}:{ctx.trace_id}"
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"",
                    }
                )

            middleware = RequestContextMiddleware(app)
            await middleware(scope, _mock_receive, _mock_send)
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
        from api.context import RequestContext, RequestIdLogFilter, request_context_var

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
                name="test",
                level=logging.INFO,
                pathname=__file__,
                lineno=42,
                msg="处理请求",
                args=(),
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
        import logging

        from api.context import RequestIdLogFilter

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=42,
            msg="服务启动中",
            args=(),
            exc_info=None,
        )
        f = RequestIdLogFilter()
        result = f.filter(record)
        assert result is True
        assert record.msg == "服务启动中"

    def test_filter_preserves_existing_trace_suffix(self):
        """已有 OTel trace 后缀时，filter 追加在 OTel 之后。"""
        from api.context import RequestContext, RequestIdLogFilter, request_context_var

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
                name="test",
                level=logging.INFO,
                pathname=__file__,
                lineno=42,
                msg="正在生成图像 [trace=abcdef1234567890]",
                args=(),
                exc_info=None,
            )
            f = RequestIdLogFilter()
            f.filter(record)
            assert "[req=req-abc-123]" in record.msg
            assert "[trace=abcdef1234567890]" in record.msg
        finally:
            request_context_var.reset(token)


# ── 辅助函数 ─────────────────────────────────


async def _mock_receive() -> dict:
    return {"type": "http.disconnect"}


async def _mock_send(message: dict) -> None:
    pass
