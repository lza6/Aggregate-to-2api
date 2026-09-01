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
from fastapi.openapi.utils import get_openapi
from fastapi.testclient import TestClient

from api import config
from api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def schema():
    """运行时生成 OpenAPI schema（与 /openapi.json 等价）。"""
    return get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        routes=app.routes,
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
        "id",
        "status",
        "prompt",
        "image_url",
        "error",
        "duration_sec",
        "created_at",
        "model",
        "client_ip",
        "client_location",
    }

    def test_taskinfo_schema_fields_stable(self, schema):
        """TaskInfo Pydantic 模型字段名集合（防后端删字段）。"""
        ti = schema["components"]["schemas"]["TaskInfo"]
        props = set(ti.get("properties", {}).keys())
        # TaskInfo 的字段集合（api/models.py:39-51）
        expected = {
            "id",
            "status",
            "image_url",
            "image_base64",
            "image_mime",
            "error",
            "created_at",
            "duration_sec",
            "type",
            "model",
            "prompt",
            "aspect_ratio",
            "client_ip",
            "client_location",
            "user_agent",
            "timings",
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
            "sitekey",
            "aspect_ratios",
            "supported_resolutions",
            "gallery_requires_password",
            "auth_enabled",
            "api_key_mask",
        }
        assert expected.issubset(body.keys()), f"/v1/meta 缺字段: {expected - set(body.keys())}"

    def test_chat_usage_fields(self, client):
        """GET /v1/chat/usage → chat_usage.py:stats() 返回（前端 ChatUsageStats）。"""
        r = client.get("/v1/chat/usage?period=24h")
        assert r.status_code == 200
        body = r.json()
        # chat_usage.py stats() 返回字段（前端 api.ts ChatUsageStats）
        expected = {
            "period",
            "total_calls",
            "ok_calls",
            "fail_calls",
            "prompt_tokens",
            "completion_tokens",
            "reasoning_tokens",
            "tool_calls",
            "avg_duration_ms",
            "today_calls",
            "today_tokens",
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
            "accounts",
            "email_pool",
            "items",
            "items_total",
            "page",
            "page_size",
            "total_pages",
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
        r = client.post(
            "/v1/admin/security/block-ip",
            json={
                "ip": "203.0.113.99",
                "block_type": "block",
                "reason": "contract-test",
                "ttl_seconds": 3600,
            },
        )
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
        """GET /v1/admin/security/blocklist → {items: [...], count: int} + P2-2 分页信封扩展字段。"""
        r = client.get("/v1/admin/security/blocklist?limit=10")
        assert r.status_code == 200
        body = r.json()
        # P2-2: 端点改分页信封 {items, count, total, page, page_size, has_more}；
        # 核心字段 items+count 必须存在，扩展字段允许存在（向后兼容契约放宽为 superset）。
        assert "items" in body
        assert "count" in body
        assert isinstance(body["items"], list)
        assert isinstance(body["count"], int)
        # 分页扩展字段（P2-2 新增）
        assert "total" in body
        assert "has_more" in body


# ── F. 统一错误响应信封契约（P1-4：防 error 信封结构漂移）─────────────
class TestErrorEnvelopeContract:
    """所有 4xx/5xx 经 handlers 统一走 error_response → {"error": {code, message, details}}。

    P1-4 统一响应契约：断言错误信封结构稳定（参考 captcha-solver SolveResponse 统一谓词）。
    后端删/改 error 字段 → 本测试 fail，强制前端错误处理同步。
    """

    def test_404_error_envelope(self, client):
        """不存在的任务 → 404 + {error: {code, message, details}}。"""
        r = client.get("/v1/tasks/nonexistent-task-id")
        assert r.status_code == 404
        body = r.json()
        assert "error" in body, "错误响应缺 error 信封"
        err = body["error"]
        assert set(err.keys()) == {"code", "message", "details"}, f"error 信封字段漂移: {set(err.keys())}"
        assert err["code"].startswith("SYS.")  # NOT_FOUND = SYS.003
        assert isinstance(err["message"], str) and err["message"]
        assert isinstance(err["details"], dict)

    def test_422_validation_error_envelope(self, client):
        """参数校验失败 → 422（FastAPI 默认结构，但经 validation_exception_handler 记录 VAL.004）。

        注：422 响应体保持 FastAPI 默认 {detail: [...]} 契约（v6.6.1 Reviewer S1 有意设计），
        不强制套 error 信封以免破坏调用方对 422 的既有解析。本例只断言状态码。
        """
        r = client.post("/v1/generate", json={})  # 缺必填 → 422
        assert r.status_code == 422

    def test_401_unauthorized_envelope(self, client, monkeypatch):
        """未鉴权访问受保护端点 → 401/403 + error 信封（AUTH.001）。"""
        # 关闭开放模式 + 配置业务 Key → 匿名访问应被拒
        monkeypatch.setattr(config.settings, "if_admin_key_open", False)
        monkeypatch.setattr(config.settings, "if_admin_keys", "admin-key-xxx")
        monkeypatch.setattr(config.settings, "if_api_keys", "biz-key-xxx")
        r = client.post("/v1/admin/security/block-ip", json={"ip": "1.2.3.4"})
        assert r.status_code in (401, 403)
        body = r.json()
        assert "error" in body
        err = body["error"]
        assert set(err.keys()) == {"code", "message", "details"}
        assert err["code"].startswith("AUTH.")  # UNAUTHORIZED = AUTH.001 / FORBIDDEN = AUTH.003

    # 注：403 IP 封禁信封（FORBIDDEN=AUTH.003）走与 404/401 完全相同的 handler 路径
    # （app_error_handler → error_response），信封结构 {error:{code,message,details}} 已由
    # test_404/test_401 传递性证明。403 的封禁命中逻辑由 test_request_guard/test_ip_blocklist 覆盖，
    # 此处不重复集成（避免 request_guard 内存缓存与 TestClient 事件循环的时序耦合导致 flaky）。



# ── E. 前端版本一致性契约（V7-4：防 landing/admin 版本漂移）──────────────
class TestFrontendVersionConsistency:
    """前端三处版本来源（landing package.json / frontend package.json / 后端 app.version）
    必须一致，杜绝「改进指南 P0-1」式 v6.5.0 vs v6.7.0 漂移。

    V7-4：CI 校验 landing 版本 == package.json 版本 == 后端 app.version。
    landing/vite.config.js 用 define.__APP_VERSION__ 注入 package.json.version，
    App.vue 页脚引用该常量；本测试断言源数据一致，防发版只改一处。
    """

    def test_landing_version_equals_backend(self):
        """landing/package.json version 必须等于 api/main.py app.version。"""
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        landing_pkg = json.loads((root / "landing" / "package.json").read_text(encoding="utf-8"))
        assert landing_pkg["version"] == app.version, (
            f"landing package.json({landing_pkg['version']}) != 后端 app.version({app.version})，"
            f"发版时只改了一处，违反版本一致性契约"
        )

    def test_frontend_version_equals_backend(self):
        """frontend/package.json version 必须等于 api/main.py app.version。"""
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        frontend_pkg = json.loads((root / "frontend" / "package.json").read_text(encoding="utf-8"))
        assert frontend_pkg["version"] == app.version, (
            f"frontend package.json({frontend_pkg['version']}) != 后端 app.version({app.version})，"
            f"违反版本一致性契约"
        )

    def test_landing_built_dist_version_matches_source(self):
        """landing 构建产物 assets/*.js 必须含当前版本字符串（防 __APP_VERSION__ 注入失效）。

        dist 由 vite build 产出（.gitignore 忽略，本地构建后才存在）；
        未构建时跳过（CI 在 deploy 前会构建，本地可 skip）。
        """
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        assets_dir = root / "landing" / "dist" / "assets"
        if not assets_dir.exists():
            pytest.skip("landing/dist 未构建，跳过产物版本断言（CI deploy 前构建）")
        version = app.version
        matched = False
        for js_file in assets_dir.glob("*.js"):
            content = js_file.read_text(encoding="utf-8", errors="ignore")
            if version in content:
                matched = True
                break
        assert matched, f"landing/dist/assets/*.js 未找到版本字符串 {version}，__APP_VERSION__ 注入可能失效"
