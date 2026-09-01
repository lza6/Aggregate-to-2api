"""api/routes/ecosystem.py 归一化与抓取单元测试（P0-2 覆盖率补强，不碰真实网络）。

覆盖 _get / _norm_models / _norm_status / _norm_today / _norm_health / _fetch_upstream
的各容错分支 + close_client + get_cache 单例。现有 test_ecosystem.py 只 patch
_fetch_upstream 走路由层，本文件直接测内部归一化函数。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import api.routes.ecosystem as eco
from api.errors import AppError


@pytest.fixture(autouse=True)
def _reset_state():
    eco._ecosystem_cache = None
    eco._last_good = None
    yield
    eco._ecosystem_cache = None
    eco._last_good = None


def _mock_response(status=200, payload=None, content_type="application/json"):
    r = MagicMock()
    r.status_code = status
    r.headers = {"content-type": content_type}
    r.json = lambda: payload if payload is not None else {}
    return r


# ── get_cache / close_client ─────────────────────────────────


def test_get_cache_singleton():
    c1 = eco.get_cache()
    c2 = eco.get_cache()
    assert c1 is c2


@pytest.mark.asyncio
async def test_close_client_noop_when_none():
    eco._client = None
    await eco.close_client()  # 不抛


@pytest.mark.asyncio
async def test_close_client_closes(monkeypatch):
    client = MagicMock()
    client.aclose = AsyncMock()
    eco._client = client
    await eco.close_client()
    assert eco._client is None


# ── _get：各容错分支 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_success(monkeypatch):
    client = MagicMock()
    client.get = AsyncMock(return_value=_mock_response(200, {"ok": True, "data": [1]}))
    monkeypatch.setattr(eco, "_get_client", lambda: client)
    r = await eco._get("/api/models")
    assert r == {"ok": True, "data": [1]}


@pytest.mark.asyncio
async def test_get_non_200_returns_none(monkeypatch):
    client = MagicMock()
    client.get = AsyncMock(return_value=_mock_response(503))
    monkeypatch.setattr(eco, "_get_client", lambda: client)
    assert await eco._get("/api/models") is None


@pytest.mark.asyncio
async def test_get_non_json_content_type(monkeypatch):
    client = MagicMock()
    client.get = AsyncMock(return_value=_mock_response(200, {}, content_type="text/html"))
    monkeypatch.setattr(eco, "_get_client", lambda: client)
    assert await eco._get("/api/models") is None


@pytest.mark.asyncio
async def test_get_non_dict_payload(monkeypatch):
    client = MagicMock()
    r = MagicMock()
    r.status_code = 200
    r.headers = {"content-type": "application/json"}
    r.json = lambda: [1, 2, 3]  # 非 dict
    client.get = AsyncMock(return_value=r)
    monkeypatch.setattr(eco, "_get_client", lambda: client)
    assert await eco._get("/api/models") is None


@pytest.mark.asyncio
async def test_get_exception_returns_none(monkeypatch):
    client = MagicMock()
    client.get = AsyncMock(side_effect=ConnectionError("network down"))
    monkeypatch.setattr(eco, "_get_client", lambda: client)
    assert await eco._get("/api/models") is None


# ── _norm_models ─────────────────────────────────────────────


def test_norm_models_unavailable():
    r = eco._norm_models(None)
    assert r == {"available": False, "last_updated": None, "count": 0, "providers": []}
    assert eco._norm_models({"ok": False})["available"] is False


def test_norm_models_success():
    raw = {
        "ok": True,
        "lastUpdated": "2026-09-01",
        "providers": [
            {"id": "p1", "name": "Provider One", "models": [{"id": "m1"}, {"id": "m2"}]},
            {"id": "p2", "name": "", "models": [{"id": "m3"}]},  # name='' (key 存在) 不回退 id
            {"id": "p3", "models": []},  # 空 models
        ],
    }
    r = eco._norm_models(raw)
    assert r["available"] is True
    assert r["count"] == 3
    # name='' 时 p.get('name', ...) 返回 ''（不回退 id）；p3 无 name key 才回退 id
    assert r["providers"][1]["name"] == ""
    assert r["providers"][2]["name"] == "p3"
    assert r["providers"][2]["models"] == []


# ── _norm_status ─────────────────────────────────────────────


def test_norm_status_unavailable():
    r = eco._norm_status(None)
    assert r["available"] is False
    assert r["all_operational"] is False


def test_norm_status_with_issues():
    raw = {
        "ok": True,
        "services": [
            {"name": "imagefree", "status": "operational", "provider": "tf"},
            {"name": "chat", "status": "degraded", "provider": "tf"},
            {"name": "no-status-svc"},  # status 缺省
        ],
    }
    r = eco._norm_status(raw)
    assert r["available"] is True
    assert r["all_operational"] is False
    assert r["service_count"] == 3
    assert len(r["issues"]) == 2  # degraded + unknown
    assert any("degraded" in i for i in r["issues"])


def test_norm_status_all_operational():
    raw = {"ok": True, "services": [{"name": "a", "status": "up"}, {"name": "b", "status": "ok"}]}
    r = eco._norm_status(raw)
    assert r["all_operational"] is True
    assert r["issues"] == []


# ── _norm_today ──────────────────────────────────────────────


def test_norm_today_unavailable():
    r = eco._norm_today(None)
    assert r == {"available": False, "news": [], "inference": {}, "papers": [], "hf": []}


def test_norm_today_success():
    raw = {
        "ok": True,
        "generated_at": "2026-09-01T00:00:00Z",
        "news": {"items": [{"t": 1}, {"t": 2}, {"t": 3}, {"t": 4}]},  # 截前 3
        "inference": {"latency": 100},
        "papers": {"ai_trending": {"papers": [{"id": "p1"}, {"id": "p2"}, {"id": "p3"}, {"id": "p4"}]}},
        "hf": {"models": {"items": [{"id": "h1"}, {"id": "h2"}]}},
    }
    r = eco._norm_today(raw)
    assert r["available"] is True
    assert r["generated_at"] == "2026-09-01T00:00:00Z"
    assert len(r["news"]) == 3
    assert r["inference"] == {"latency": 100}
    assert len(r["papers"]) == 3
    assert len(r["hf"]) == 2


def test_norm_today_hf_not_list():
    raw = {"ok": True, "hf": {"models": "not-a-dict-with-items"}}
    r = eco._norm_today(raw)
    assert r["hf"] == []


# ── _norm_health ──────────────────────────────────────────────


def test_norm_health_unavailable():
    r = eco._norm_health(None)
    assert r == {"available": False, "news_count": None, "model_count": None}


def test_norm_health_success():
    raw = {"ok": True, "news": {"totalArticles": 42}, "models": {"count": 15}}
    r = eco._norm_health(raw)
    assert r == {"available": True, "news_count": 42, "model_count": 15}


# ── _fetch_upstream：聚合 + 全失败抛 502 ────────────────────


@pytest.mark.asyncio
async def test_fetch_upstream_all_failed_raises_502(monkeypatch):
    async def fake_get(path):
        return None

    monkeypatch.setattr(eco, "_get", fake_get)
    with pytest.raises(AppError) as exc:
        await eco._fetch_upstream()
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_fetch_upstream_partial_success(monkeypatch):
    async def fake_get(path):
        if path == "/api/models":
            return {"ok": True, "lastUpdated": "x", "providers": [{"id": "p", "models": []}]}
        return None  # 其余失败

    monkeypatch.setattr(eco, "_get", fake_get)
    payload = await eco._fetch_upstream()
    assert payload["models"]["available"] is True
    assert payload["status"]["available"] is False
    assert payload["today"]["available"] is False
    assert payload["health"]["available"] is False
    assert "cache" in payload
