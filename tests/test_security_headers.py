"""P3-3: CORS/CSP 安全头收紧 smoke 测试。

验证 SecurityHeadersMiddleware 按 IF_SECURITY_HEADERS_ENABLED / IF_CSP_ENABLED 注入响应头，
且默认配置不破坏现状（CORS 仍为 * 全放行、无 CSP 头注入）。

环境隔离注意：
- 通过 monkeypatch.setenv 在 import api.config 前设定 IF_ 环境变量，
  使 config 单例（settings）在第一次实例化时读到目标值。若接口早已被其它测试
  导入，无法重置单例，因此本用例用「子进程」方式验证开关开关效果更稳，但为了
  在现有 pytest 体系内低成本跑通，这里使用 httpx ASGITransport 调真实 app，
  断言默认启用时的安全头。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


class _NoopApp:
    """ASGI noop app：直接返回 200，用于直接测中间件逻辑（不经路由）。"""

    async def __call__(self, scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"ok"})


class TestSecurityHeaders:
    """默认配置（IF_SECURITY_HEADERS_ENABLED=true）下安全头注入。"""

    async def test_security_headers_present_on_healthz(self, _app_instance):
        """IF_SECURITY_HEADERS_ENABLED=True（默认）时，/v1/healthz 响应应含安全头。"""
        from api import config

        if not config.IF_SECURITY_HEADERS_ENABLED:
            pytest.skip("IF_SECURITY_HEADERS_ENABLED=False，未注入安全头，跳过断言")

        async with AsyncClient(
            transport=ASGITransport(app=_app_instance.app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/healthz")
            # healthz 可能返回 degraded，但 200 是稳定契约
            assert r.status_code == 200
            assert r.headers.get("x-content-type-options") == "nosniff"
            assert r.headers.get("x-frame-options") == "DENY"
            assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    async def test_default_csp_disabled(self, _app_instance):
        """默认 IF_CSP_ENABLED=False：不应注入 Content-Security-Policy（避免误杀面板/画廊）。"""
        from api import config

        if config.IF_CSP_ENABLED:
            pytest.skip("IF_CSP_ENABLED=True，本用例验证默认关闭行为，跳过")

        async with AsyncClient(
            transport=ASGITransport(app=_app_instance.app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/healthz")
            assert r.status_code == 200
            assert "content-security-policy" not in r.headers

    async def test_request_id_still_injected(self, _app_instance):
        """回归：RequestContextMiddleware 的 X-Request-ID 与安全头共存，不互相覆盖。"""
        async with AsyncClient(
            transport=ASGITransport(app=_app_instance.app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/healthz")
            assert r.status_code == 200
            assert r.headers.get("x-request-id")

    @pytest.mark.asyncio
    async def test_csp_enabled_injects_header(self):
        """P1-2: IF_CSP_ENABLED=True 时注入 Content-Security-Policy 头（生产收紧试点验证）。"""
        import api.main

        mw = api.main.SecurityHeadersMiddleware(_NoopApp())
        mw._enabled = True
        mw._csp_enabled = True  # 模拟生产开启 CSP

        seen: dict = {}

        async def cap(message):
            if message["type"] == "http.response.start":
                seen.update({k.lower().decode(): v.decode() for k, v in message["headers"]})

        await mw({"type": "http", "scheme": "https", "headers": [], "path": "/x"}, None, cap)
        assert "content-security-policy" in seen
        csp = seen["content-security-policy"]
        # CSP 常量含 default-src 'self' + img-src（画廊图源域名白名单）
        assert "default-src 'self'" in csp
        assert "img-src" in csp

    @pytest.mark.asyncio
    async def test_csp_disabled_no_header(self):
        """P1-2: IF_CSP_ENABLED=False（默认）不注入 CSP（向后兼容）。"""
        import api.main

        mw = api.main.SecurityHeadersMiddleware(_NoopApp())
        mw._enabled = True
        mw._csp_enabled = False  # 默认关闭

        seen: dict = {}

        async def cap(message):
            if message["type"] == "http.response.start":
                seen.update({k.lower().decode(): v.decode() for k, v in message["headers"]})

        await mw({"type": "http", "scheme": "https", "headers": [], "path": "/x"}, None, cap)
        assert "content-security-policy" not in seen

    @pytest.mark.asyncio
    async def test_security_headers_off_when_disabled(self):
        """P1-2: IF_SECURITY_HEADERS_ENABLED=False 时不注入任何安全头（最小回滚）。"""
        import api.main

        mw = api.main.SecurityHeadersMiddleware(_NoopApp())
        mw._enabled = False  # 模拟关闭
        mw._csp_enabled = True  # 即使 CSP 开关 true，主开关 false 也不注入

        seen: dict = {}

        async def cap(message):
            if message["type"] == "http.response.start":
                seen.update({k.lower().decode(): v.decode() for k, v in message["headers"]})

        await mw({"type": "http", "scheme": "https", "headers": [], "path": "/x"}, None, cap)
        assert "x-content-type-options" not in seen
        assert "content-security-policy" not in seen

    @pytest.mark.asyncio
    async def test_hsts_only_on_https(self):
        """Strict-Transport-Security 仅在 scheme=https 时注入（直接测中间件逻辑）。"""
        import api.main

        async def endpoint(scope, receive, send):
            # 直接发送响应，绕过路由
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"ok"})

        async def capture(scheme: str) -> dict:
            mw = api.main.SecurityHeadersMiddleware(endpoint)
            seen: dict = {}

            async def cap(message):
                if message["type"] == "http.response.start":
                    seen.update({k.lower().decode(): v.decode() for k, v in message["headers"]})

            await mw({"type": "http", "scheme": scheme, "headers": [], "path": "/x"}, None, cap)
            return seen

        headers_http = await capture("http")
        headers_https = await capture("https")

        assert headers_http.get("strict-transport-security") is None
        assert headers_https.get("strict-transport-security") == "max-age=31536000; includeSubDomains"
        # 非 HTTPS 路径仍注入其余安全头
        assert headers_http.get("x-content-type-options") == "nosniff"
        assert headers_https.get("x-content-type-options") == "nosniff"
