"""v4.4.3: 全站写操作鉴权 + 调用方 IP 落库/展示 测试。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import guard_generate_request, _client_ip_of, public_keymask
from api.handlers import register_exception_handlers
from api.routes.generate import router as generate_router
from api.routes.chat import router as chat_router
from api.config import Settings


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
    import api.config as config_module
    config_module.settings = Settings()
    return TestClient(make_app())


def test_client_ip_xff_preferred():
    from types import SimpleNamespace
    class Req:
        headers = {"x-forwarded-for": "203.0.113.99, 10.0.0.5"}
        client = SimpleNamespace(host="172.25.0.1")
    assert _client_ip_of(Req()) == "203.0.113.99"


def test_client_ip_falls_back_to_socket():
    from types import SimpleNamespace
    class Req2:
        headers = {}
        client = SimpleNamespace(host="8.8.8.8")
    assert _client_ip_of(Req2()) == "8.8.8.8"


def test_keymask_hides_tail(monkeypatch):
    monkeypatch.setenv("IF_API_KEYS", "sk-tfai-abcdef1234567890")
    import api.config as config_module
    config_module.settings = Settings()
    mask = public_keymask()
    assert mask.startswith("sk-")
    assert "***" in mask and "abcdef1234567890" not in mask


def test_generate_without_key_401(client):
    r = client.post("/v1/generate/async", json={"prompt": "t", "aspect_ratio": "1:1"})
    assert r.status_code == 401


def test_generate_with_key_passes_guard(client, monkeypatch):
    # 拦截 generate 模块内对 _dispatch_generate 的引用，验证路由已把真实客户端 IP 回填到 req.client_ip
    import api.routes.generate as gen_mod

    captured = {}
    async def fake_dispatch(req):
        captured["client_ip"] = getattr(req, "client_ip", None)
        return "fake-task"

    async def fake_get_public(tid):
        return {"id": tid, "status": "pending", "image_url": None, "error": None,
                "created_at": 0, "duration_sec": None, "model": "default",
                "type": "txt", "prompt": "t", "aspect_ratio": "1:1", "client_ip": None}
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