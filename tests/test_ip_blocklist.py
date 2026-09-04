"""ISSUE-02: 动态 IP 风控与封禁引擎测试。

覆盖闭环：
- IPBlocklistStore 增删查、批量检查、TTL 过期与过期清理
- request_guard 风控：block 403 / daily_limit 403 / TTL 过期放行 / 白名单绕过
- 频繁超限自动入黑名单（真实异步落地）
- 管理面安全端点（block-ip / unblock-ip / blocklist / status）与鉴权
"""

from __future__ import annotations

import asyncio
import time

import pytest
import pytest_asyncio
from starlette.requests import Request

from api import config
from api.errors import AppError, ErrorCodes

# 模块级单例（在 fixture 中原地改 _path 实现每用例隔离 DB）
from api.db.ip_blocklist_store import ip_blocklist_store as store
import api.request_guard as rg


# ── 工具 / fixtures ────────────────────────────────────────────


def _make_request(ip: str) -> Request:
    """构造带 X-Forwarded-For 头的 Starlette Request（模拟反代后的真实客户端 IP）。"""
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/generate",
        "raw_path": b"/v1/generate",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"x-forwarded-for", ip.encode()),
            (b"host", b"testserver"),
            (b"user-agent", b"pytest"),
        ],
        "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8000),
        "state": {},
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _reset_guard_state():
    """每个用例前重置 request_guard 内存级缓存与计数（隔离用例间状态）。"""
    rg.reset_runtime_state()
    yield
    rg.reset_runtime_state()


@pytest_asyncio.fixture
async def blocklist_store(tmp_path):
    """把单例 store 指向独立临时 DB，保证每用例真正隔离。"""
    old_path = store._path
    store._path = str(tmp_path / "ip_blocklist.db")
    store._initialized = False
    yield store
    store._path = old_path
    store._initialized = False


async def _add_and_apply(ip: str, **kwargs) -> dict:
    """写入封禁表并立即应用内存缓存（模拟管理面端点的即时生效路径）。"""
    rec = await store.add_or_update(ip=ip, **kwargs)
    rg.apply_ip_rule(ip, rec)
    return rec


# ── IPBlocklistStore：增删查 / TTL / 批量 ─────────────────────────


class TestIPBlocklistStore:
    async def test_add_and_get(self, blocklist_store):
        rec = await blocklist_store.add_or_update(
            ip="203.0.113.9",
            block_type="block",
            reason="test",
            ttl_seconds=600,
        )
        assert rec["ip"] == "203.0.113.9"
        assert rec["block_type"] == "block"
        assert rec["expire_at"] > time.time()

        got = await blocklist_store.get("203.0.113.9")
        assert got is not None
        assert got["reason"] == "test"
        assert got["daily_limit"] == 1

    async def test_update_keeps_created_at(self, blocklist_store):
        await blocklist_store.add_or_update(ip="203.0.113.10", block_type="block", reason="first")
        rec = await blocklist_store.add_or_update(
            ip="203.0.113.10",
            block_type="daily_limit",
            daily_limit=5,
            reason="second",
        )
        assert rec["block_type"] == "daily_limit"
        assert rec["daily_limit"] == 5
        assert rec["reason"] == "second"
        assert rec["created_at"] > 0  # 首次创建后不再重置
        assert rec["updated_at"] >= rec["created_at"]

    async def test_remove(self, blocklist_store):
        await blocklist_store.add_or_update(ip="203.0.113.11", block_type="block")
        assert await blocklist_store.remove("203.0.113.11") is True
        assert await blocklist_store.get("203.0.113.11") is None
        assert await blocklist_store.remove("203.0.113.11") is False

    async def test_get_expired_returns_none(self, blocklist_store):
        await blocklist_store.add_or_update(ip="203.0.113.12", block_type="block", ttl_seconds=0.05)
        await asyncio.sleep(0.1)
        assert await blocklist_store.get("203.0.113.12") is None

    async def test_list_excludes_expired(self, blocklist_store):
        await blocklist_store.add_or_update(ip="203.0.113.13", block_type="block", ttl_seconds=0)
        await blocklist_store.add_or_update(ip="203.0.113.14", block_type="block", ttl_seconds=0.05)
        await asyncio.sleep(0.1)
        ips = {item["ip"] for item in await blocklist_store.list_all()}
        assert "203.0.113.13" in ips
        assert "203.0.113.14" not in ips

    async def test_cleanup_expired(self, blocklist_store):
        await blocklist_store.add_or_update(ip="203.0.113.15", block_type="block", ttl_seconds=0.05)
        await asyncio.sleep(0.1)
        assert await blocklist_store.cleanup_expired() == 1
        assert await blocklist_store.get("203.0.113.15") is None

    async def test_get_many_batch(self, blocklist_store):
        await blocklist_store.add_or_update(ip="203.0.113.16", block_type="block", ttl_seconds=0)
        await blocklist_store.add_or_update(
            ip="203.0.113.17",
            block_type="daily_limit",
            daily_limit=3,
            ttl_seconds=0,
        )
        await blocklist_store.add_or_update(ip="203.0.113.18", block_type="block", ttl_seconds=0.05)
        await asyncio.sleep(0.1)
        out = await blocklist_store.get_many(["203.0.113.16", "203.0.113.17", "203.0.113.18", "203.0.113.99"])
        assert set(out) == {"203.0.113.16", "203.0.113.17"}  # 已过期/不存在的不会出现
        assert out["203.0.113.17"]["daily_limit"] == 3

    async def test_get_many_empty_input(self, blocklist_store):
        assert await blocklist_store.get_many([]) == {}


# ── P2-2 分页 + count + since_ts ─────────────────────────────


class TestPaginationAndCount:
    async def test_list_all_pagination_offset(self, blocklist_store):
        """list_all(limit, offset) 返回正确的页切片（按 updated_at DESC）。"""
        for i in range(25):
            await blocklist_store.add_or_update(
                ip=f"203.0.114.{i}",
                block_type="block",
                reason=f"r{i}",
                ttl_seconds=0,
            )
        page1 = await blocklist_store.list_all(limit=10, offset=0)
        page2 = await blocklist_store.list_all(limit=10, offset=10)
        page3 = await blocklist_store.list_all(limit=10, offset=20)
        assert len(page1) == 10
        assert len(page2) == 10
        assert len(page3) == 5  # 25 - 20 = 5
        # 三页互不重叠
        ips_all = {item["ip"] for item in page1 + page2 + page3}
        assert len(ips_all) == 25
        # 按 updated_at DESC：page1 的 updated_at 都 >= page2 的
        assert page1[-1]["updated_at"] >= page2[0]["updated_at"]

    async def test_list_all_limit_clamped(self, blocklist_store):
        """limit 钳制到 [1, 10000]：0 → 1，100000 → 10000。"""
        await blocklist_store.add_or_update(ip="203.0.114.50", block_type="block", ttl_seconds=0)
        # limit=0 → 钳到 1，至少返回 1 条
        res = await blocklist_store.list_all(limit=0)
        assert len(res) == 1
        # limit 巨大 → 钳到 10000，不会崩
        res_big = await blocklist_store.list_all(limit=100000)
        assert len(res_big) == 1

    async def test_count_returns_total(self, blocklist_store):
        """count() 返回有效记录总数（不加载全部数据）。"""
        for i in range(5):
            await blocklist_store.add_or_update(
                ip=f"203.0.115.{i}",
                block_type="block",
                ttl_seconds=0,
            )
        assert await blocklist_store.count() == 5

    async def test_count_excludes_expired(self, blocklist_store):
        """count() 排除已过期记录（与 list_all 一致）。"""
        await blocklist_store.add_or_update(ip="203.0.116.1", block_type="block", ttl_seconds=0)
        await blocklist_store.add_or_update(ip="203.0.116.2", block_type="block", ttl_seconds=0.05)
        await asyncio.sleep(0.1)
        assert await blocklist_store.count() == 1  # 过期的不计

    async def test_list_all_since_ts_filter(self, blocklist_store):
        """list_all(since_ts=) 只返回 updated_at >= since_ts 的记录。"""
        t0 = time.time()
        await blocklist_store.add_or_update(ip="203.0.117.1", block_type="block", ttl_seconds=0)
        await asyncio.sleep(0.05)
        t_mid = time.time()
        await blocklist_store.add_or_update(ip="203.0.117.2", block_type="block", ttl_seconds=0)

        recent = await blocklist_store.list_all(limit=100, offset=0, since_ts=t_mid)
        ips = {item["ip"] for item in recent}
        assert "203.0.117.2" in ips
        assert "203.0.117.1" not in ips  # t0~t_mid 之间，被过滤

        all_recent = await blocklist_store.list_all(limit=100, offset=0, since_ts=t0)
        assert len(all_recent) == 2

    async def test_count_since_ts_filter(self, blocklist_store):
        """count(since_ts=) 只计 updated_at >= since_ts 的记录。"""
        t0 = time.time()
        await blocklist_store.add_or_update(ip="203.0.118.1", block_type="block", ttl_seconds=0)
        await asyncio.sleep(0.05)
        t_mid = time.time()
        await blocklist_store.add_or_update(ip="203.0.118.2", block_type="block", ttl_seconds=0)
        assert await blocklist_store.count(since_ts=t_mid) == 1
        assert await blocklist_store.count(since_ts=t0) == 2


# ── request_guard：风控闭环 ─────────────────────────────────────


class TestRequestGuard:
    async def test_blocked_ip_403(self, blocklist_store, monkeypatch):
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)
        await _add_and_apply("203.0.113.20", block_type="block", reason="spam")
        with pytest.raises(AppError) as ei:
            rg.check_generate_request(_make_request("203.0.113.20"))
        assert ei.value.status_code == 403
        assert ei.value.code == ErrorCodes.FORBIDDEN

    async def test_unblocked_ip_passes(self, blocklist_store, monkeypatch):
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)
        await _add_and_apply("203.0.113.21", block_type="block")
        await store.remove("203.0.113.21")
        rg.invalidate_ip_cache("203.0.113.21")
        rg.check_generate_request(_make_request("203.0.113.21"))  # 解封后放行，不抛异常

    async def test_daily_limit_403_after_n(self, blocklist_store, monkeypatch):
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)
        await _add_and_apply(
            "203.0.113.22",
            block_type="daily_limit",
            daily_limit=2,
            reason="limited",
        )
        rg.check_generate_request(_make_request("203.0.113.22"))
        rg.check_generate_request(_make_request("203.0.113.22"))
        with pytest.raises(AppError) as ei:
            rg.check_generate_request(_make_request("203.0.113.22"))
        assert ei.value.status_code == 403
        assert ei.value.code == ErrorCodes.FORBIDDEN

    async def test_ttl_expiry_allows_request(self, blocklist_store, monkeypatch):
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)
        await _add_and_apply("203.0.113.23", block_type="block", ttl_seconds=0.1, reason="temp")
        with pytest.raises(AppError):
            rg.check_generate_request(_make_request("203.0.113.23"))
        await asyncio.sleep(0.15)  # TTL 过期
        rg.check_generate_request(_make_request("203.0.113.23"))  # 放行
        assert await store.get("203.0.113.23") is None

    async def test_whitelist_bypasses_block(self, blocklist_store, monkeypatch):
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)
        monkeypatch.setattr(config, "IF_IP_WHITELIST", "203.0.113.24")
        await _add_and_apply("203.0.113.24", block_type="block", reason="blocked")
        rg.check_generate_request(_make_request("203.0.113.24"))  # 白名单直接放行

    async def test_whitelist_bypasses_rate_limit(self, blocklist_store, monkeypatch):
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 2)
        monkeypatch.setattr(config, "IF_IP_WHITELIST", "203.0.113.25")
        for _ in range(5):  # 远超 2 次/分钟仍全部放行
            rg.check_generate_request(_make_request("203.0.113.25"))

    async def test_auto_block_after_repeated_429(self, blocklist_store, monkeypatch):
        # v7.6 flaky 根修：显式先建表。原实现依赖 _auto_block_ip task 里的
        # add_or_update 首次建表——轮询期间多个 fire-and-forget task 并发竞态
        # （init_schema check-then-act + Windows tmp DB 首连慢），偶发
        # "no such table: ip_blocklist" → 403 永不出现 → assert blocked 失败。
        await blocklist_store.init_schema()
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 2)
        monkeypatch.setattr(config, "IF_AUTO_BLOCK_ENABLED", True)
        monkeypatch.setattr(config, "IF_AUTO_BLOCK_THRESHOLD", 2)
        monkeypatch.setattr(config, "IF_AUTO_BLOCK_WINDOW_SECONDS", 60)
        monkeypatch.setattr(config, "IF_AUTO_BLOCK_TTL_SECONDS", 3600)
        ip = "203.0.113.26"

        rg.check_generate_request(_make_request(ip))  # 第 1 次通过
        rg.check_generate_request(_make_request(ip))  # 第 2 次通过
        with pytest.raises(AppError) as e1:
            rg.check_generate_request(_make_request(ip))  # 第 3 次 429（超限 #1）
        assert e1.value.status_code == 429
        with pytest.raises(AppError) as e2:
            rg.check_generate_request(_make_request(ip))  # 第 4 次 429（超限 #2 → 触发自动封禁）
        assert e2.value.status_code == 429

        # 轮询等待异步自动封禁落地（不再用固定 sleep，防 CI 慢机）。
        # v7.6 flaky 根治双保险：① 用例开头显式 init_schema 预建表，消除
        # "首次建表发生在并发 429 task 中"的竞态；② 轮询预算 250×0.02s=5s，
        # 覆盖 Windows 本机 tmp DB 首连 + Defender 实扫偶发延迟（CI ubuntu <100ms）。
        blocked = False
        for _ in range(250):
            try:
                rg.check_generate_request(_make_request(ip))
            except AppError as e:
                if e.status_code == 403:
                    blocked = True
                    break
                if e.status_code != 429:
                    raise
            await asyncio.sleep(0.02)
        assert blocked, "自动封禁未在预期时间内生效（5s）"

        got = await store.get(ip)
        assert got is not None and got["block_type"] == "block"
        assert got["reason"] == "rate-limit-exceeded"

    async def test_auto_block_disabled(self, blocklist_store, monkeypatch):
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 2)
        monkeypatch.setattr(config, "IF_AUTO_BLOCK_ENABLED", False)
        monkeypatch.setattr(config, "IF_AUTO_BLOCK_THRESHOLD", 1)
        ip = "203.0.113.27"

        rg.check_generate_request(_make_request(ip))
        rg.check_generate_request(_make_request(ip))
        with pytest.raises(AppError) as e3:
            rg.check_generate_request(_make_request(ip))  # 第 3 次 429
        assert e3.value.status_code == 429
        await asyncio.sleep(0.05)
        assert await store.get(ip) is None  # 未自动封禁

    async def test_block_then_guard_403_closed_loop(self, blocklist_store, monkeypatch):
        """闭环：管理面端点封禁 → 该 IP 的生成请求立即 403（不依赖全量同步空窗）。"""
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)
        monkeypatch.setattr(config.settings, "if_api_keys", "")
        monkeypatch.setattr(config.settings, "if_admin_keys", "")
        monkeypatch.setattr(config.settings, "if_admin_key_open", True)  # 开放模式跑闭环
        from fastapi import FastAPI
        from httpx import AsyncClient, ASGITransport
        from api.routes.security import router as security_router
        from api.handlers import register_exception_handlers

        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(security_router)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/v1/admin/security/block-ip",
                json={
                    "ip": "203.0.113.30",
                    "block_type": "block",
                    "reason": "e2e",
                },
            )
            assert r.status_code == 200

        with pytest.raises(AppError) as ei:
            rg.check_generate_request(_make_request("203.0.113.30"))
        assert ei.value.status_code == 403


# ── 管理面安全端点（HTTP）───────────────────────────────────────


@pytest_asyncio.fixture
async def security_client(blocklist_store, monkeypatch):
    """独立 FastAPI 应用：仅挂载安全路由 + 全局异常处理器。"""
    monkeypatch.setattr(config.settings, "if_api_keys", "")  # 无业务 Key
    monkeypatch.setattr(config.settings, "if_admin_keys", "")
    monkeypatch.setattr(config.settings, "if_admin_key_open", True)  # 显式开放（本地运维模式）
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from api.routes.security import router as security_router
    from api.handlers import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(security_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestSecurityEndpoints:
    async def test_block_unblock_list_status(self, security_client):
        # 封禁
        r = await security_client.post(
            "/v1/admin/security/block-ip",
            json={
                "ip": "203.0.113.7",
                "block_type": "block",
                "reason": "api test",
                "ttl_seconds": 3600,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True and data["record"]["ip"] == "203.0.113.7"
        assert data["record"]["expire_at"] > time.time()

        # 状态查询
        r = await security_client.get("/v1/admin/security/status", params={"ip": "203.0.113.7"})
        assert r.status_code == 200
        assert r.json()["blocked"] is True

        # 列表
        r = await security_client.get("/v1/admin/security/blocklist")
        assert r.status_code == 200
        assert any(item["ip"] == "203.0.113.7" for item in r.json()["items"])

        # 解封
        r = await security_client.delete("/v1/admin/security/unblock-ip", params={"ip": "203.0.113.7"})
        assert r.status_code == 200
        assert r.json()["removed"] is True

        r = await security_client.get("/v1/admin/security/status", params={"ip": "203.0.113.7"})
        assert r.json()["blocked"] is False

    async def test_block_daily_limit_via_api(self, security_client):
        r = await security_client.post(
            "/v1/admin/security/block-ip",
            json={
                "ip": "203.0.113.8",
                "block_type": "daily_limit",
                "daily_limit": 5,
                "ttl_seconds": 86400,
            },
        )
        assert r.status_code == 200
        assert r.json()["record"]["block_type"] == "daily_limit"
        assert r.json()["record"]["daily_limit"] == 5

    async def test_block_validation(self, security_client):
        # 非法 IP
        r = await security_client.post("/v1/admin/security/block-ip", json={"ip": "999.1.2.3"})
        assert r.status_code == 400
        # 非法 block_type
        r = await security_client.post(
            "/v1/admin/security/block-ip",
            json={
                "ip": "203.0.113.7",
                "block_type": "ban",
            },
        )
        assert r.status_code == 400
        # daily_limit < 1
        r = await security_client.post(
            "/v1/admin/security/block-ip",
            json={
                "ip": "203.0.113.7",
                "block_type": "daily_limit",
                "daily_limit": 0,
            },
        )
        assert r.status_code == 400
        # 空 IP
        r = await security_client.delete("/v1/admin/security/unblock-ip", params={"ip": ""})
        assert r.status_code == 400

    async def test_security_dedicated_admin_key(self, blocklist_store, monkeypatch):
        """ISSUE-02 加固：独立 IF_ADMIN_KEYS 优先生效；无任何 Key 时默认 403 拒绝。"""
        from fastapi import FastAPI
        from httpx import AsyncClient, ASGITransport
        from api.routes.security import router as security_router
        from api.handlers import register_exception_handlers

        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(security_router)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # 场景 A：独立管理 Key 配置 → 业务 Key 不能操作管理面
            monkeypatch.setattr(config.settings, "if_api_keys", "sk-biz-key")
            monkeypatch.setattr(config.settings, "if_admin_keys", "sk-admin-key")
            monkeypatch.setattr(config.settings, "if_admin_key_open", False)
            r = await c.get("/v1/admin/security/blocklist", headers={"X-API-Key": "sk-biz-key"})
            assert r.status_code == 401
            r = await c.get("/v1/admin/security/blocklist", headers={"X-API-Key": "sk-admin-key"})
            assert r.status_code == 200

            # 场景 B：无任何 Key 且未开放 → 默认拒绝（403）
            monkeypatch.setattr(config.settings, "if_api_keys", "")
            monkeypatch.setattr(config.settings, "if_admin_keys", "")
            monkeypatch.setattr(config.settings, "if_admin_key_open", False)
            r = await c.get("/v1/admin/security/blocklist")
            assert r.status_code == 403

    async def test_security_requires_api_key(self, blocklist_store, monkeypatch):
        """未配置独立管理 Key 时继承业务 Key（兼容降级）。"""
        monkeypatch.setattr(config.settings, "if_api_keys", "sk-test-key")
        monkeypatch.setattr(config.settings, "if_admin_keys", "")
        monkeypatch.setattr(config.settings, "if_admin_key_open", False)
        from fastapi import FastAPI
        from httpx import AsyncClient, ASGITransport
        from api.routes.security import router as security_router
        from api.handlers import register_exception_handlers

        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(security_router)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # 未携带 Key → 401
            r = await c.get("/v1/admin/security/blocklist")
            assert r.status_code == 401
            r = await c.get("/v1/admin/security/blocklist", headers={"X-API-Key": "wrong-key"})
            assert r.status_code == 401
            # 正确 Key → 200
            r = await c.get("/v1/admin/security/blocklist", headers={"X-API-Key": "sk-test-key"})
            assert r.status_code == 200
