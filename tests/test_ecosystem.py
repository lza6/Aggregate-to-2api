"""TensorFeed AI 生态端点（/v1/ai-ecosystem）单元测试。

覆盖：
- 端点 200 且聚合字段正确
- 缓存命中（第二次调用不打上游）
- 并发防击穿（只 fetch 一次）
- 上游失败回退 stale
- 无缓存失败抛 502

所有上游交互通过 monkeypatch _fetch_upstream 控制（不碰真实网络）。
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.errors import AppError, ErrorCodes
from api.handlers import app_error_handler
from api.routes import ecosystem


@pytest.fixture
def app(monkeypatch):
    """独立 FastAPI 应用，仅挂载 ecosystem 路由 + AppError 处理器。
    预置一个空缓存与计数器，避免跨用例污染。"""
    monkeypatch.setattr(ecosystem, "_ecosystem_cache", None)
    monkeypatch.setattr(ecosystem, "_last_good", None)
    monkeypatch.setattr(ecosystem, "_fetch_lock", asyncio.Lock())
    monkeypatch.setattr(ecosystem, "_client", None)

    application = FastAPI()
    application.add_exception_handler(AppError, app_error_handler)
    application.include_router(ecosystem.router)
    return application


async def request(application: FastAPI, url: str = "/v1/ai-ecosystem"):
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        return await client.get(url)


def _fake_payload():
    """构造一个完整的假聚合响应。"""
    return {
        "models": {
            "available": True,
            "last_updated": "2026-08-30T00:00:00Z",
            "count": 2,
            "providers": [
                {"id": "openai", "name": "OpenAI",
                 "models": [{"id": "gpt-4", "name": "GPT-4", "inputPrice": 30,
                             "outputPrice": 60, "contextWindow": 128000,
                             "tier": "paid", "released": "2024"}]},
                {"id": "deepseek", "name": "DeepSeek",
                 "models": [{"id": "deepseek-v3", "name": "DeepSeek V3",
                             "inputPrice": 0, "outputPrice": 0,
                             "contextWindow": 64000, "tier": "free", "released": "2024"}]},
            ],
        },
        "status": {
            "available": True, "all_operational": True, "service_count": 2,
            "services": [{"name": "OpenAI API", "status": "operational", "provider": "openai"},
                         {"name": "DeepSeek API", "status": "operational", "provider": "deepseek"}],
            "issues": [],
        },
        "today": {
            "available": True, "generated_at": "2026-08-30T01:00:00Z",
            "news": [{"title": "GPT-5 发布", "source": "OpenAI", "url": "https://x", "publishedAt": "2026-08-30"}],
            "inference": {"total_models": 2, "cheapest_input": 0, "cheapest_output": 0,
                          "largest_context": 128000, "free_tier_count": 1,
                          "top_namespaces": ["openai", "deepseek"]},
            "papers": [],
            "hf": [],
        },
        "health": {"available": True, "news_count": 100, "model_count": 2},
        "cache": {"ttl_seconds": 900, "fetched_from_upstream_at": 1},
    }


# ── 1. 端点 200 且聚合字段正确 ──────────────────────


@pytest.mark.asyncio
async def test_endpoint_200_and_fields(app, monkeypatch):
    calls = {"n": 0}

    async def fake_fetch():
        calls["n"] += 1
        return _fake_payload()

    monkeypatch.setattr(ecosystem, "_fetch_upstream", fake_fetch)

    resp = await request(app)
    assert resp.status_code == 200
    body = resp.json()

    assert body["models"]["count"] == 2
    assert body["models"]["available"] is True
    assert len(body["models"]["providers"]) == 2
    assert body["status"]["all_operational"] is True
    assert body["status"]["service_count"] == 2
    assert body["today"]["available"] is True
    assert len(body["today"]["news"]) >= 1
    assert body["health"]["news_count"] == 100
    assert body["cache"]["ttl_seconds"] == 900
    assert calls["n"] == 1


# ── 2. 缓存命中（第二次调用不打上游）────────────────


@pytest.mark.asyncio
async def test_cache_hit_skips_upstream(app, monkeypatch):
    calls = {"n": 0}

    async def fake_fetch():
        calls["n"] += 1
        return _fake_payload()

    monkeypatch.setattr(ecosystem, "_fetch_upstream", fake_fetch)

    r1 = await request(app)
    assert r1.status_code == 200
    r2 = await request(app)
    assert r2.status_code == 200
    # 第二次应命中缓存，不再调用 _fetch_upstream
    assert calls["n"] == 1


# ── 3. 并发防击穿（并发请求只 fetch 一次）────────────


@pytest.mark.asyncio
async def test_concurrent_no_thundering_herd(app, monkeypatch):
    calls = {"n": 0}

    async def fake_fetch():
        calls["n"] += 1
        # 模拟上游慢，让并发请求都在锁前等待
        await asyncio.sleep(0.05)
        return _fake_payload()

    monkeypatch.setattr(ecosystem, "_fetch_upstream", fake_fetch)

    # 5 个并发请求
    results = await asyncio.gather(*(request(app) for _ in range(5)))
    assert all(r.status_code == 200 for r in results)
    # 防击穿：5 个并发只触发一次上游抓取
    assert calls["n"] == 1


# ── 4. 上游失败回退 stale ──────────────────────────


@pytest.mark.asyncio
async def test_upstream_failure_falls_back_to_stale(app, monkeypatch):
    calls = {"n": 0}

    async def fake_fetch():
        calls["n"] += 1
        # 第一次成功，第二次失败
        if calls["n"] == 1:
            return _fake_payload()
        raise AppError(ErrorCodes.UPSTREAM_ERROR, "上游不可用", status_code=502)

    monkeypatch.setattr(ecosystem, "_fetch_upstream", fake_fetch)
    # 使用短 TTL 缓存使第二次请求缓存未命中
    from api.cache import LRUCache
    short_cache = LRUCache(maxsize=8, ttl=0.05)
    monkeypatch.setattr(ecosystem, "_ecosystem_cache", short_cache)

    r1 = await request(app)
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1.get("stale") is None or b1.get("stale") is False

    # 等缓存过期
    await asyncio.sleep(0.1)

    r2 = await request(app)
    assert r2.status_code == 200
    b2 = r2.json()
    # 回退到 _last_good 并标记 stale
    assert b2.get("stale") is True
    assert b2["models"]["count"] == 2


# ── 5. 无缓存 + 上游失败 → 502 ───────────────────────


@pytest.mark.asyncio
async def test_no_cache_upstream_failure_returns_502(app, monkeypatch):
    async def fake_fetch():
        raise AppError(ErrorCodes.UPSTREAM_ERROR, "上游不可用", status_code=502)

    monkeypatch.setattr(ecosystem, "_fetch_upstream", fake_fetch)

    resp = await request(app)
    assert resp.status_code == 502
    body = resp.json()
    assert body["error"]["code"] == ErrorCodes.UPSTREAM_ERROR


# ── 6. 部分端点失败（逐段容错）──────────────────────


@pytest.mark.asyncio
async def test_partial_upstream_failure_degrades_gracefully(app, monkeypatch):
    """四个上游端点中部分失败，仍返回 available=True 的段，失败段 available=False。"""
    # 直接 patch _get 让 /api/models 与 /api/today 返回 None，其余正常
    # 注意：绝不用 original_get 兜底其余段——它走真实 TensorFeed 上游，全量跑（前序文件
    # 已 import api.main 且 MOCK_UPSTREAM 未必生效）会命中真实网络 → 502。
    # 剩余段也各返回一个模拟 payload（status/today/health 有数据 → available=True）。
    async def fake_get(path):
        return {
            "/api/models": None,
            "/api/today": None,
            "/api/status": {"ok": True, "services": [{"name": "s", "status": "ok"}]},
        }.get(path, {"ok": True})

    monkeypatch.setattr(ecosystem, "_get", fake_get)

    resp = await request(app)
    assert resp.status_code == 200
    body = resp.json()
    # models 段不可用，status/today/health 至少一个可用
    assert body["models"]["available"] is False
    assert body["models"]["count"] == 0
    # 至少一个段可用，整体不抛 502
    assert any(body[k]["available"] for k in ("status", "today", "health"))


# ── 7. 路由已注册到主应用 ───────────────────────────


def test_route_registered_in_main_app():
    """冒烟：api.main.app 路由表中存在 /v1/ai-ecosystem。

    遍历 _IncludedRouter.original_router.routes（fastapi 新版 include_router 把
    api_router 包成 _IncludedRouter，子路由在 original_router.routes 上）。
    """
    import api.main

    def walk(routes):
        for r in routes:
            path = getattr(r, "path", "")
            if path:
                yield path
            # fastapi 新版：include_router 包成 _IncludedRouter，子路由在 original_router
            orig = getattr(r, "original_router", None)
            if orig is not None and hasattr(orig, "routes"):
                yield from walk(orig.routes)
            # starlette APIRouter：routes 属性直接持有子路由
            sub = getattr(r, "routes", None)
            if sub:
                yield from walk(sub)
            # Mount：app 可能是另一个 Starlette/FastAPI 实例
            inner = getattr(r, "app", None)
            if inner is not None and inner is not r and hasattr(inner, "routes"):
                yield from walk(inner.routes)

    paths = list(walk(api.main.app.routes))
    assert "/v1/ai-ecosystem" in paths, f"路由未注册：前 20 个路径 {paths[:20]}"
