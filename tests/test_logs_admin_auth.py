"""v7.7.8: /v1/logs 端点鉴权测试（公益开放只读）。

覆盖：
- 开放模式 / 配置 Key / 独立 admin key → /v1/logs 均 200（v7.7.8 起对访客只读开放）
- ?api_key= query 不落入访问日志（脱敏通道不回归）
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
    """配置了 IF_API_KEYS（v7.7.8：/v1/logs 仍只读开放）。"""
    monkeypatch.setenv("IF_API_KEYS", "sk-test-key-12345")
    monkeypatch.setenv("IF_ADMIN_KEYS", "")
    monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "")
    import api.config as config_module
    from api.config import Settings

    config_module.settings = Settings()
    return TestClient(_make_app())


@pytest.fixture()
def admin_secured_client(monkeypatch):
    """配置了独立 IF_ADMIN_KEYS（v7.7.8：/v1/logs 仍只读开放）。"""
    monkeypatch.setenv("IF_API_KEYS", "sk-test-key-12345")
    monkeypatch.setenv("IF_ADMIN_KEYS", "sk-admin-key-67890")
    monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "")
    import api.config as config_module
    from api.config import Settings

    config_module.settings = Settings()
    return TestClient(_make_app())


class TestLogsAdminAuth:
    def test_open_mode_allows_logs(self, open_mode_client):
        """开放模式放行 /v1/logs。"""
        r = open_mode_client.get("/v1/logs?lines=10")
        assert r.status_code == 200
        assert "logs" in r.json()

    def test_secured_allows_without_key(self, secured_client):
        """v7.7.8：配置了业务 Key 时，/v1/logs 无 key 也放行（公益只读开放）。"""
        r = secured_client.get("/v1/logs?lines=10")
        assert r.status_code == 200

    def test_secured_accepts_with_admin_key(self, secured_client):
        """携带 admin key（继承业务 Key）→ 200。"""
        r = secured_client.get("/v1/logs?lines=10", headers={"Authorization": "Bearer sk-test-key-12345"})
        assert r.status_code == 200

    def test_admin_secured_allows_without_key(self, admin_secured_client):
        """v7.7.8：配置了独立 admin key 时，/v1/logs 无 key 也放行（公益只读开放）。"""
        r = admin_secured_client.get("/v1/logs?lines=10")
        assert r.status_code == 200

    def test_admin_secured_accepts_correct_key(self, admin_secured_client):
        """正确 admin key 放行。"""
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
        # snapshot 返回 list[dict]（每条日志是 dict），需把 dict 序列化后再拼接扫描
        import json

        joined = "\n".join(
            e if isinstance(e, str) else json.dumps(e, ensure_ascii=False, default=str)
            for e in snapshot
        )
        assert "sk-secret-leak-test-123" not in joined, "完整 api_key 不应落入访问日志"
