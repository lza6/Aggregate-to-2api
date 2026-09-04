"""v4.4: 聊天 API Key 鉴权 + /v1/chat/models 端点测试。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.config import Settings
from api.routes.chat import router


def make_app(auth_keys: str = "") -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture()
def client_no_auth(monkeypatch):
    monkeypatch.setenv("IF_API_KEYS", "")
    import api.config as config_module

    config_module.settings = Settings()
    app = make_app("")
    return TestClient(app)


@pytest.fixture()
def client_with_auth(monkeypatch):
    monkeypatch.setenv("IF_API_KEYS", "sk-test-abc,sk-test-xyz")
    import api.config as config_module

    config_module.settings = Settings()
    app = make_app("sk-test-abc")
    return TestClient(app)


# ── /v1/chat/auth/status ──


def test_auth_status_open(client_no_auth):
    resp = client_no_auth.get("/v1/chat/auth/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    # P0: 开放模式无完整 key 可给
    assert body["key"] == ""


def test_auth_status_enabled(client_with_auth):
    resp = client_with_auth.get("/v1/chat/auth/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True


# ── P0: /v1/chat/auth/status 与 /v1/meta 不得匿名泄漏完整 key ──
def test_auth_status_does_not_leak_key_anonymous(client_with_auth):
    """管理面板一键复制是唯一入口；匿名/无管理 Key 回调不得带回完整 key。"""
    resp = client_with_auth.get("/v1/chat/auth/status")
    body = resp.json()
    assert body["key"] == "", "匿名（未带管理 Key）回调不得泄漏完整 key"
    assert body["key_mask"]  # 仅脱敏前缀可公开
    assert body["key"] != body["key_mask"]  # 前缀绝不能等于完整 key


def test_meta_does_not_leak_full_key(client_with_auth):
    """P3-9 线上复核回归：/v1/meta 是公开只读探测端点，匿名响应不得包含完整 API Key，
    只允许返回脱敏前缀 api_key_mask 与鉴权开关 auth_enabled。"""
    from api.routes.health import router as health_router

    app = FastAPI()
    app.include_router(health_router)
    client = TestClient(app)
    resp = client.get("/v1/meta")
    assert resp.status_code == 200
    body = resp.json()
    # 公开探测只暴露脱敏前缀 + 开关，绝不暴露完整 key
    assert "api_key_mask" in body
    assert body.get("api_key_mask", "").endswith("***") or "***" in body.get("api_key_mask", "")
    # 不存在任何完整 key 字段
    assert "key" not in body or body.get("key") in (None, "")
    # mask 不等于任一真实 key
    assert body["api_key_mask"] not in {"sk-test-abc", "sk-test-xyz"}


def test_auth_status_admin_can_copy_key(client_with_auth, monkeypatch):
    """携带管理面有效 Key（或继承业务 Key）时，站长可一键复制完整 key。"""
    from fastapi import Request

    def _fake_admin(request: Request, *, scope: str = "admin-security") -> None:
        return None

    # chat_auth_status 在函数体内 from ..auth import (...)，故需 patch 源模块 api.auth
    monkeypatch.setattr("api.auth.check_admin_key", _fake_admin)
    monkeypatch.setattr("api.auth.first_key", lambda: "sk-full-secret")
    monkeypatch.setattr("api.auth.admin_enabled", lambda: True)
    resp = client_with_auth.get("/v1/chat/auth/status")
    assert resp.status_code == 200
    assert resp.json()["key"] == "sk-full-secret"


# ── P0 安全回归：匿名不得获取完整 Key ──


def test_auth_status_no_full_key_anonymous(client_with_auth):
    """匿名（无 Key）请求 /v1/chat/auth/status 不得返回完整 key，只回 mask。"""
    resp = client_with_auth.get("/v1/chat/auth/status")
    body = resp.json()
    assert body["enabled"] is True
    # 完整 key 不应暴露（除非携带管理 Key）
    assert body.get("key") == "" or body.get("key") is None
    # 脱敏前缀仍在
    assert body["key_mask"].endswith("***") or "***" in body["key_mask"]


def test_auth_status_admin_key_gets_full(client_with_auth):
    """携带管理面有效 Key 时，/v1/chat/auth/status 才返回完整 key（站长复制）。"""
    resp = client_with_auth.get(
        "/v1/chat/auth/status",
        headers={"Authorization": "Bearer sk-test-abc"},
    )
    body = resp.json()
    assert body["enabled"] is True
    assert body["key"] == "sk-test-abc"


def test_auth_status_wrong_admin_key_no_full(client_with_auth):
    """携带错误管理 Key 时，/v1/chat/auth/status 不返回完整 key。"""
    resp = client_with_auth.get(
        "/v1/chat/auth/status",
        headers={"Authorization": "Bearer sk-wrong"},
    )
    body = resp.json()
    assert body.get("key") == "" or body.get("key") is None


# ── /v1/chat/models ──


def test_chat_models_lists_tryingopen(client_no_auth):
    resp = client_no_auth.get("/v1/chat/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 13
    ids = [m["id"] for m in body["items"]]
    assert any(mid.startswith("tryingopen/") for mid in ids)
    glm = next((m for m in body["items"] if "glm-5.3-flash" in m["id"]), None)
    assert glm is not None
    assert "chat" in glm["capabilities"]


# ── Key 校验：聊天端点强制 Bearer ──

PAYLOAD = {
    "model": "tryingopen/z-ai/glm-5.3-flash",
    "messages": [{"role": "user", "content": "hi"}],
}


def make_app_with_error_handler() -> FastAPI:
    """带 AppError 全局处理器的 app（与生产 handlers.register_exception_handlers 等价）。"""
    from api.handlers import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    return app


@pytest.fixture()
def client_auth_handler(monkeypatch):
    monkeypatch.setenv("IF_API_KEYS", "sk-test-abc,sk-test-xyz")
    import api.config as config_module

    config_module.settings = Settings()
    return TestClient(make_app_with_error_handler())


def test_completions_open_without_key(client_auth_handler, monkeypatch):
    # v7.7.1：公益定位——聊天端点不再强制 IF_API_KEYS 业务 Key，无 key 也放行（不限 key）。
    # mock provider，避免真实上游调用
    from api.providers.registry import registry

    class FakeProvider:
        async def chat_collect(self, model, messages, **kw):
            return {"text": "pong", "finish_reason": "stop"}

    monkeypatch.setitem(
        registry.chat_providers, "tryingopen", FakeProvider()
    )
    resp = client_auth_handler.post("/v1/chat/completions", json=PAYLOAD)
    assert resp.status_code in (200, 429)


def test_completions_open_with_any_key(client_auth_handler, monkeypatch):
    # v7.7.1：聊天不再校验 key 对错，任意/错误 key 同样放行（仅 per-IP 频控）。
    from api.providers.registry import registry

    class FakeProvider:
        async def chat_collect(self, model, messages, **kw):
            return {"text": "pong", "finish_reason": "stop"}

    monkeypatch.setitem(
        registry.chat_providers, "tryingopen", FakeProvider()
    )
    resp = client_auth_handler.post(
        "/v1/chat/completions",
        json=PAYLOAD,
        headers={"Authorization": "Bearer sk-wrong"},
    )
    assert resp.status_code in (200, 429)


def test_completions_accepts_valid_key(client_auth_handler, monkeypatch):
    # mock provider，避免真实上游调用
    class FakeProvider:
        async def chat_collect(self, model, messages, **kw):
            return {
                "text": "pong",
                "reasoning": "",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                "finish_reason": "stop",
            }

    from api.providers.registry import registry

    monkeypatch.setitem(registry.chat_providers, "tryingopen", FakeProvider())
    # models 目录也给一个假 spec 让 _provider_for 通过
    from api.providers.base import ModelSpec

    spec = ModelSpec(
        id="tryingopen/z-ai/glm-5.3-flash",
        provider="tryingopen",
        upstream_model="z-ai/glm-5.3-flash",
        capabilities=("chat",),
    )
    monkeypatch.setattr(registry, "chat_model", lambda mid: spec)

    for headers in (
        {"Authorization": "Bearer sk-test-abc"},
        {"X-API-Key": "sk-test-xyz"},
    ):
        resp = client_auth_handler.post("/v1/chat/completions", json=PAYLOAD, headers=headers)
        assert resp.status_code == 200, headers
        assert resp.json()["choices"][0]["message"]["content"] == "pong"


def test_completions_open_mode_no_key_needed(client_no_auth, monkeypatch):
    class FakeProvider:
        async def chat_collect(self, model, messages, **kw):
            return {"text": "hi", "reasoning": "", "usage": None, "finish_reason": "stop"}

    from api.providers.registry import registry

    monkeypatch.setitem(registry.chat_providers, "tryingopen", FakeProvider())
    from api.providers.base import ModelSpec

    spec = ModelSpec(
        id="tryingopen/z-ai/glm-5.3-flash",
        provider="tryingopen",
        upstream_model="z-ai/glm-5.3-flash",
        capabilities=("chat",),
    )
    monkeypatch.setattr(registry, "chat_model", lambda mid: spec)

    resp = client_no_auth.post("/v1/chat/completions", json=PAYLOAD)
    assert resp.status_code == 200


# ── 挂载回归：chat.router 必须真实挂在 api_router 上（防止 import 未 include 的伪实现）──


def test_chat_router_is_mounted_on_api_router():
    from api.routes import api_router

    def _flatten(router):
        """递归展平 FastAPI 0.141 的 _IncludedRouter（嵌套 API Router）。"""
        out: set[str] = set()
        for r in router.routes:
            orig = getattr(r, "original_router", None)
            if orig is not None:
                out |= _flatten(orig)
            else:
                p = getattr(r, "path", "")
                if p:
                    out.add(p)
        return out

    mounted_paths = _flatten(api_router)
    assert "/v1/chat/completions" in mounted_paths
    assert "/v1/chat/models" in mounted_paths
    assert "/v1/messages" in mounted_paths
