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


def test_auth_status_enabled(client_with_auth):
    resp = client_with_auth.get("/v1/chat/auth/status")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


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


def test_completions_rejects_missing_key(client_auth_handler):
    resp = client_auth_handler.post("/v1/chat/completions", json=PAYLOAD)
    assert resp.status_code == 401


def test_completions_rejects_wrong_key(client_auth_handler):
    resp = client_auth_handler.post(
        "/v1/chat/completions",
        json=PAYLOAD,
        headers={"Authorization": "Bearer sk-wrong"},
    )
    assert resp.status_code == 401


def test_completions_accepts_valid_key(client_auth_handler, monkeypatch):
    # mock provider，避免真实上游调用
    class FakeProvider:
        async def chat_collect(self, model, messages, **kw):
            return {"text": "pong", "reasoning": "", "usage": {"prompt_tokens": 1,
                    "completion_tokens": 1, "total_tokens": 2}, "finish_reason": "stop"}

    from api.providers.registry import registry
    monkeypatch.setitem(registry.chat_providers, "tryingopen", FakeProvider())
    # models 目录也给一个假 spec 让 _provider_for 通过
    from api.providers.base import ModelSpec
    spec = ModelSpec(id="tryingopen/z-ai/glm-5.3-flash", provider="tryingopen",
                     upstream_model="z-ai/glm-5.3-flash", capabilities=("chat",))
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
    spec = ModelSpec(id="tryingopen/z-ai/glm-5.3-flash", provider="tryingopen",
                     upstream_model="z-ai/glm-5.3-flash", capabilities=("chat",))
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
