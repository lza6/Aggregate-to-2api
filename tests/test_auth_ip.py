"""v4.4.3: 全站写操作鉴权 + 调用方 IP 落库/展示 测试。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import _client_ip_of, public_keymask
from api.config import Settings
from api.handlers import register_exception_handlers
from api.routes.chat import router as chat_router
from api.routes.generate import router as generate_router


def make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(generate_router)
    app.include_router(chat_router)
    return app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("IF_API_KEYS", "sk-test-abc,sk-test-xyz")
    monkeypatch.setenv("IF_REQUESTS_PER_MINUTE", "0")  # 关闭 per-IP 限流隔离 Key 测试
    # TestClient 的对端是 'testclient'，不属受信代理；把该对端加入受信代理使 XFF 可被解析（仅测试环境）。
    # Settings 单例在 import 时固化 env，故需同时刷新模块级常量（request_guard 读模块常量）。
    monkeypatch.setenv("IF_TRUSTED_PROXIES", "testclient,127.0.0.1,::1")
    import api.config as config_module

    config_module.settings = Settings()
    config_module.IF_TRUSTED_PROXIES = config_module.settings.if_trusted_proxies
    return TestClient(make_app())


def test_client_ip_xff_preferred():
    """ISSUE-02 安全加固后：socket 非受信代理时 XFF 不生效（回退 socket）。"""
    from types import SimpleNamespace

    class Req:
        headers = {"x-forwarded-for": "203.0.113.99, 10.0.0.5"}
        client = SimpleNamespace(host="172.25.0.1")

    assert _client_ip_of(Req()) == "172.25.0.1"


def test_client_ip_falls_back_to_socket():
    from types import SimpleNamespace

    class Req2:
        headers = {}
        client = SimpleNamespace(host="8.8.8.8")

    assert _client_ip_of(Req2()) == "8.8.8.8"


def test_client_ip_trusted_proxy_rightmost():
    """受信代理（127.0.0.1）+ 客户端前置 XFF 时应取 XFF 最右非代理段。"""
    from types import SimpleNamespace

    class Req3:
        headers = {"x-forwarded-for": "203.0.113.5, 198.51.100.7"}
        client = SimpleNamespace(host="127.0.0.1")

    assert _client_ip_of(Req3()) == "198.51.100.7"


def test_keymask_hides_tail(monkeypatch):
    monkeypatch.setenv("IF_API_KEYS", "sk-tfai-abcdef1234567890")
    import api.config as config_module

    config_module.settings = Settings()
    mask = public_keymask()
    assert mask.startswith("sk-")
    assert "***" in mask and "abcdef1234567890" not in mask


def test_meta_anonymous_no_full_key(monkeypatch):
    """P0 安全回归：匿名 GET /v1/meta 不得返回完整 api_key（只回 mask）。

    /v1/meta 在 health router（test_auth_ip 的 make_app 未挂），故此处直接测 health.
    """
    import api.config as config_module

    monkeypatch.setenv("IF_API_KEYS", "sk-test-abc")
    config_module.settings = Settings()

    from fastapi import FastAPI

    from api.routes.health import router as health_router

    app = FastAPI()
    from api.handlers import register_exception_handlers

    register_exception_handlers(app)
    app.include_router(health_router)
    c = TestClient(app)
    resp = c.get("/v1/meta")
    assert resp.status_code == 200
    body = resp.json()
    assert "api_key" not in body, "/v1/meta 不应泄露完整 api_key"
    assert "***" in body["api_key_mask"]
    assert body["auth_enabled"] is True


def test_generate_without_key_open(client):
    # v7.7.1：公益定位——生图/图生图不再强制 IF_API_KEYS 业务 Key，无 key 也放行（200/202/429）。
    # 配 key 仅用于 stats 等可选鉴权场景，不再限制生图调用。
    r = client.post("/v1/generate/async", json={"prompt": "t", "aspect_ratio": "1:1"})
    assert r.status_code in (200, 202, 429)


def test_generate_with_key_passes_guard(client, monkeypatch):
    # 拦截 generate 模块内对 _dispatch_generate 的引用，验证路由已把真实客户端 IP 回填到 req.client_ip
    import api.routes.generate as gen_mod

    captured = {}

    async def fake_dispatch(req):
        captured["client_ip"] = getattr(req, "client_ip", None)
        return "fake-task"

    async def fake_get_public(tid):
        return {
            "id": tid,
            "status": "pending",
            "image_url": None,
            "error": None,
            "created_at": 0,
            "duration_sec": None,
            "model": "default",
            "type": "txt",
            "prompt": "t",
            "aspect_ratio": "1:1",
            "client_ip": None,
        }

    monkeypatch.setattr(gen_mod, "_dispatch_generate", fake_dispatch)
    monkeypatch.setattr(gen_mod.db, "get_public", fake_get_public)
    monkeypatch.setattr(gen_mod, "QueueFull", type("QF", (), {}))

    # 同步验证 generate 模块内引用到的是我们打的补丁（防 import 级快照问题）
    assert gen_mod._dispatch_generate is fake_dispatch

    r = client.post(
        "/v1/generate/async",
        json={"prompt": "t", "aspect_ratio": "1:1"},
        headers={"Authorization": "Bearer sk-test-abc", "X-Forwarded-For": "203.0.113.7"},
    )
    assert r.status_code == 200, r.text
    assert captured.get("client_ip") == "203.0.113.7"
    assert captured.get("client_ip") == "203.0.113.7"
