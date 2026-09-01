"""P3-6: /v1/logs 端点管理 Key 鉴权测试。

覆盖：
- 未配置任何 Key（IF_ADMIN_KEY_OPEN=1 开放模式）→ 放行
- 配置 IF_API_KEYS → /v1/logs 需 admin key，无 key 401
- 配置 IF_ADMIN_KEYS → /v1/logs 需 admin key，无 key 401
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.handlers import register_exception_handlers
from api.routes.admin import router as admin_router


def _make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(admin_router)
    return app


@pytest.fixture()
def open_mode_client(monkeypatch):
    """开放模式：无 Key + IF_ADMIN_KEY_OPEN=1 → 放行。"""
    monkeypatch.setenv("IF_API_KEYS", "")
    monkeypatch.setenv("IF_ADMIN_KEYS", "")
    monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "1")
    import api.config as config_module
    from api.config import Settings

    config_module.settings = Settings()
    return TestClient(_make_app())


@pytest.fixture()
def secured_client(monkeypatch):
    """配置了 IF_API_KEYS → /v1/logs 需 admin key。"""
    monkeypatch.setenv("IF_API_KEYS", "sk-test-key-12345")
    monkeypatch.setenv("IF_ADMIN_KEYS", "")
    monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "")
    import api.config as config_module
    from api.config import Settings

    config_module.settings = Settings()
    return TestClient(_make_app())


@pytest.fixture()
def admin_secured_client(monkeypatch):
    """配置了独立 IF_ADMIN_KEYS → /v1/logs 需 admin key。"""
    monkeypatch.setenv("IF_API_KEYS", "sk-test-key-12345")
    monkeypatch.setenv("IF_ADMIN_KEYS", "sk-admin-key-67890")
    monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "")
    import api.config as config_module
    from api.config import Settings

    config_module.settings = Settings()
    return TestClient(_make_app())


class TestLogsAdminAuth:
    def test_open_mode_allows_logs(self, open_mode_client):
        """开放模式（无 Key + ADMIN_KEY_OPEN=1）放行 /v1/logs。"""
        r = open_mode_client.get("/v1/logs?lines=10")
        assert r.status_code == 200
        assert "logs" in r.json()

    def test_secured_rejects_without_key(self, secured_client):
        """配置了业务 Key 时，/v1/logs 无 key → 401。"""
        r = secured_client.get("/v1/logs?lines=10")
        assert r.status_code == 401

    def test_secured_accepts_with_admin_key(self, secured_client):
        """配置了业务 Key 时，/v1/logs 携带 admin key（继承业务 Key）→ 200。"""
        r = secured_client.get("/v1/logs?lines=10", headers={"Authorization": "Bearer sk-test-key-12345"})
        assert r.status_code == 200

    def test_admin_secured_rejects_wrong_key(self, admin_secured_client):
        """配置了独立 admin key 时，业务 key 不能访问 /v1/logs。"""
        r = admin_secured_client.get(
            "/v1/logs?lines=10", headers={"Authorization": "Bearer sk-test-key-12345"}
        )
        assert r.status_code == 401

    def test_admin_secured_accepts_correct_key(self, admin_secured_client):
        """配置了独立 admin key 时，正确 admin key 放行。"""
        r = admin_secured_client.get(
            "/v1/logs?lines=10", headers={"Authorization": "Bearer sk-admin-key-67890"}
        )
        assert r.status_code == 200


class TestApiKeyQueryMask:
    """P3-6: ?api_key= query 传 Key 不应落入访问日志。"""

    def test_access_log_excludes_query_string(self, open_mode_client):
        """访问日志只记 path（不含 ?api_key=xxx query）。"""
        # 触发一次带 ?api_key= 的请求
        r = open_mode_client.get("/v1/logs?lines=5&api_key=sk-secret-leak-test-123")
        assert r.status_code == 200
        # 从 log_buffer snapshot 中不应出现完整 api_key 值
        from api.log_buffer import log_buffer

        snapshot = log_buffer.snapshot(200)
        joined = "\n".join(snapshot)
        assert "sk-secret-leak-test-123" not in joined, "完整 api_key 不应落入访问日志"
