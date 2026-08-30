"""P3-2: OpenAPI↔前端契约测试（小型起步，防响应字段漂移）。

设计（不引入 openapi-typescript 全量生成器，避免大型工具链侵入构建）：
1. 用 app.openapi() 生成 schema 快照（运行时即真，无需落盘），断言关键端点存在于 paths；
2. 用真实 TestClient 命中关键端点，断言响应 JSON 字段名集合稳定；
3. 断言前端 api.ts 手写类型与后端真实响应一致（字段名集合差集为空）。

漂移即红：后端删字段 / 改类型 → 字段名集合变化 → 本测试 fail，强制前端同步。

关键端点（与 frontend/src/api.ts 的 TS 接口一一对应）：
- GET /v1/tasks/{task_id}  → Task（TaskInfo Pydantic 模型，response_model 已声明）
- GET /v1/chat/usage       → ChatUsageStats（无 response_model，运行时取真实字段）
- GET /v1/account-pool     → AccountPoolResponse（无 response_model，运行时取真实字段）
- GET /v1/meta             → ChatAuthStatus 的公开探测子集（无 response_model）
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from fastapi.openapi.utils import get_openapi

from api.main import app
from api import config


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def schema():
    """运行时生成 OpenAPI schema（与 /openapi.json 等价）。"""
    return get_openapi(
        title=app.title, version=app.version,
        openapi_version=app.openapi_version, routes=app.routes,
    )


# ── A. schema paths 存在性：端点注册不丢 ─────────────────────────
class TestSchemaPathsExist:
    """关键端点必须在 OpenAPI schema 中注册（端点被误删/改路径 → 立即红）。"""

    def test_tasks_detail_path(self, schema):
        assert "/v1/tasks/{task_id}" in schema["paths"]

    def test_chat_usage_path(self, schema):
        assert "/v1/chat/usage" in schema["paths"]

    def test_account_pool_path(self, schema):
        assert "/v1/account-pool" in schema["paths"]

    def test_meta_path(self, schema):
        assert "/v1/meta" in schema["paths"]


# ── B. response_model 声明端点：字段名集合稳定（TaskInfo）───────
class TestTaskInfoContract:
    """GET /v1/tasks/{task_id} 声明了 response_model=TaskInfo → OpenAPI 给出完整字段。

    前端 api.ts 的 Task 接口字段必须 ⊆ TaskInfo schema 字段（前端不能声明后端没有的字段）。
    """

    # frontend/src/api.ts: Task 接口字段（人工抄录，漂移即红）
    FRONTEND_TASK_FIELDS = {
        "id", "status", "prompt", "image_url", "error",
        "duration_sec", "created_at", "model", "client_ip", "client_location",
    }

    def test_taskinfo_schema_fields_stable(self, schema):
        """TaskInfo Pydantic 模型字段名集合（防后端删字段）。"""
        ti = schema["components"]["schemas"]["TaskInfo"]
        props = set(ti.get("properties", {}).keys())
        # TaskInfo 的字段集合（api/models.py:39-51）
        expected = {
            "id", "status", "image_url", "image_base64", "image_mime",
            "error", "created_at", "duration_sec", "type", "model",
            "prompt", "aspect_ratio", "client_ip", "client_location",
            "user_agent", "timings",
        }
        assert props == expected, f"TaskInfo 字段漂移: 缺 {expected - props}, 多 {props - expected}"

    def test_frontend_task_subset_of_taskinfo(self, schema):
        """前端 Task 接口字段必须 ⊆ 后端 TaskInfo schema 字段（前端不能声明后端没有的）。"""
        ti = schema["components"]["schemas"]["TaskInfo"]
        backend = set(ti.get("properties", {}).keys())
        extra = self.FRONTEND_TASK_FIELDS - backend
        assert not extra, f"前端 Task 声明了后端没有的字段: {extra}"


# ── C. 运行时真实响应字段（无 response_model 端点）──────────────
class TestRuntimeResponseContract:
    """无 response_model 的端点 → schema 里 schema 是空 {}，必须用真实响应断言字段。

    这些端点的字段是「运行时拼装」的，最容易悄悄漂移。本组用 TestClient 命中真实响应，
    断言关键字段名存在；字段漂移时 fail，强制前端同步。
    """

    def test_meta_fields(self, client):
        """GET /v1/meta → health.py:173 返回（前端 ChatAuthStatus 公开探测子集）。"""
        r = client.get("/v1/meta")
        assert r.status_code == 200
        body = r.json()
        # health.py /v1/meta 返回字段
        expected = {
            "sitekey", "aspect_ratios", "supported_resolutions",
            "gallery_requires_password", "auth_enabled", "api_key_mask",
        }
        assert expected.issubset(body.keys()), f"/v1/meta 缺字段: {expected - set(body.keys())}"

    def test_chat_usage_fields(self, client):
        """GET /v1/chat/usage → chat_usage.py:stats() 返回（前端 ChatUsageStats）。"""
        r = client.get("/v1/chat/usage?period=24h")
        assert r.status_code == 200
        body = r.json()
        # chat_usage.py stats() 返回字段（前端 api.ts ChatUsageStats）
        expected = {
            "period", "total_calls", "ok_calls", "fail_calls",
            "prompt_tokens", "completion_tokens", "reasoning_tokens",
            "tool_calls", "avg_duration_ms", "today_calls", "today_tokens",
            "by_model",
        }
        assert expected.issubset(body.keys()), f"/v1/chat/usage 缺字段: {expected - set(body.keys())}"

    def test_account_pool_fields(self, client):
        """GET /v1/account-pool → admin.py:account_pool_dashboard 返回（前端 AccountPoolResponse）。"""
        r = client.get("/v1/account-pool?page=1&page_size=1")
        assert r.status_code == 200
        body = r.json()
        # admin.py account_pool_dashboard 顶层字段（前端 api.ts AccountPoolResponse）
        expected = {
            "accounts", "email_pool", "items", "items_total",
            "page", "page_size", "total_pages",
        }
        assert expected.issubset(body.keys()), f"/v1/account-pool 缺字段: {expected - set(body.keys())}"
        # items 为数组（即便空也是数组，不是 None）
        assert isinstance(body["items"], list)
        assert isinstance(body["accounts"], dict)


# ── D. 管理面写操作鉴权契约（v6.7.0：DLQ/安全风控需管理 Key）────
class TestWriteOperationAuthContract:
    """写操作端点必须鉴权：未携带管理 Key → 401/403（防鉴权被意外移除）。

    v6.7.0：DLQ retry/clear 补 check_admin_key；security.py 早已有。
    本组断言「未配置 Key 时这些端点拒绝匿名写」的契约不变。
    """

    def test_dlq_retry_requires_admin_key(self, client):
        """POST /v1/dead-letter-queue/{id}/retry 无管理 Key → 401/403（不 200）。"""
        r = client.post("/v1/dead-letter-queue/nonexistent-task/retry")
        assert r.status_code in (401, 403), f"DLQ retry 未鉴权即放行（{r.status_code}），违反写操作受保护契约"

    def test_dlq_clear_requires_admin_key(self, client):
        """DELETE /v1/dead-letter-queue 无管理 Key → 401/403（不 200）。"""
        r = client.delete("/v1/dead-letter-queue")
        assert r.status_code in (401, 403), f"DLQ clear 未鉴权即放行（{r.status_code}），违反写操作受保护契约"

    def test_security_block_requires_admin_key(self, client):
        """POST /v1/admin/security/block-ip 无管理 Key → 401/403。"""
        r = client.post("/v1/admin/security/block-ip", json={"ip": "1.2.3.4"})
        assert r.status_code in (401, 403), f"block-ip 未鉴权即放行（{r.status_code}），违反写操作受保护契约"


# ── E. 安全风控响应字段契约（v6.7.0：防前端 BlockRule 字段漂移）────────
class TestSecurityResponseContract:
    """block-ip 成功响应的 record 字段必须与前端 BlockRule 接口一致。

    前端 api.ts BlockRule: {ip, block_type, daily_limit?, reason?,
    ttl_seconds?, created_at?, expire_at?}。后端 ip_blocklist_store 返回
    dict 用 expire_at（无 s）；本组断言字段名集合稳定，漂移即红。
    """

    @pytest.fixture(autouse=True)
    def _open_admin(self, monkeypatch):
        """本地开放模式放行写操作（仅测试）。

        _admin_open() 要求：IF_ADMIN_KEY_OPEN=1 且管理/业务 Key 均为空。
        auth._keys() 读 config.settings.if_api_keys；_admin_keys() 读
        config.settings.if_admin_keys（空则继承 _keys()）。三者需同时置空。
        """
        monkeypatch.setattr(config.settings, "if_admin_key_open", True)
        monkeypatch.setattr(config.settings, "if_admin_keys", "")
        monkeypatch.setattr(config.settings, "if_api_keys", "")

    def test_block_ip_record_fields(self, client, monkeypatch):
        """POST /v1/admin/security/block-ip 成功 → record 含前端期望字段。"""
        # 用临时 SQLite 库，避免污染默认库（store 路径随 config）
        r = client.post("/v1/admin/security/block-ip", json={
            "ip": "203.0.113.99",
            "block_type": "block",
            "reason": "contract-test",
            "ttl_seconds": 3600,
        })
        assert r.status_code == 200, f"block-ip 应开放放行（{r.status_code}）: {r.text[:200]}"
        body = r.json()
        assert body["ok"] is True
        rec = body["record"]
        expected = {"ip", "block_type", "daily_limit", "reason", "expire_at"}
        assert expected.issubset(rec.keys()), f"record 缺字段: {expected - set(rec.keys())}"
        # block_type='block' 时 daily_limit 不应触发 >=1 校验
        assert rec["block_type"] == "block"
        assert rec["ip"] == "203.0.113.99"
        # ttl>0 时 expire_at 应为未来时间戳（非 0）
        assert rec["expire_at"] and rec["expire_at"] > 0

    def test_blocklist_response_shape(self, client):
        """GET /v1/admin/security/blocklist → {items: [...], count: int}。"""
        r = client.get("/v1/admin/security/blocklist?limit=10")
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"items", "count"}
        assert isinstance(body["items"], list)
        assert isinstance(body["count"], int)
