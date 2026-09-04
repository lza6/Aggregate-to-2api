"""P2-3: /v1/system 与 /v1/meta ETag 协商缓存测试（直接调端点函数，免 TestClient lifespan 卡顿）。

覆盖：首次 200 + ETag 头、If-None-Match 匹配 → 304 空体、不匹配 → 200、
payload 变化 → ETag 变化、meta 不泄露完整 Key。

设计：用 mock Request/Response 直接调 system_info/meta 异步函数，绕过 TestClient
完整 lifespan startup（单独跑时 lifespan 等待真实网络依赖会卡住，与 ETag 逻辑无关）。
"""

from __future__ import annotations

import hashlib
import json

import pytest

from api.routes.health import meta, system_info
from api import system_spec as ss


class FakeResponse:
    def __init__(self) -> None:
        self.status_code = 200
        self.headers: dict[str, str] = {}

    def __setitem__(self, key: str, value) -> None:
        self.headers[key] = value


def _make_request(headers: dict[str, str] | None = None):
    req = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    req.headers = headers or {}
    return req


def _expected_etag(payload: dict) -> str:
    return '"' + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:32] + '"'


# ── /v1/system ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_system_first_request_200_with_etag():
    resp = FakeResponse()
    payload = await system_info(_make_request(), resp)
    assert resp.status_code == 200
    assert resp.headers["ETag"] == _expected_etag(payload)
    assert "cpu" in payload


@pytest.mark.asyncio
async def test_system_if_none_match_returns_304():
    resp1 = FakeResponse()
    await system_info(_make_request(), resp1)
    etag = resp1.headers["ETag"]

    resp2 = FakeResponse()
    body = await system_info(_make_request({"if-none-match": etag}), resp2)
    assert resp2.status_code == 304
    assert resp2.headers["ETag"] == etag
    assert body == {}  # 304 空 body


@pytest.mark.asyncio
async def test_system_mismatched_etag_returns_200():
    resp = FakeResponse()
    payload = await system_info(_make_request({"if-none-match": '"stale"'}), resp)
    assert resp.status_code == 200
    assert payload["cpu"]["cores"] == ss.CPU_COUNT


@pytest.mark.asyncio
async def test_system_etag_stable_when_spec_unchanged():
    """连续两次请求（无变化）→ ETag 相同。"""
    r1 = FakeResponse()
    await system_info(_make_request(), r1)
    e1 = r1.headers["ETag"]
    r2 = FakeResponse()
    await system_info(_make_request(), r2)
    e2 = r2.headers["ETag"]
    assert e1 == e2


# ── /v1/meta ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_meta_first_200_with_etag():
    resp = FakeResponse()
    payload = await meta(_make_request(), resp)
    assert resp.status_code == 200
    assert resp.headers["ETag"] == _expected_etag(payload)
    assert "sitekey" in payload


@pytest.mark.asyncio
async def test_meta_if_none_match_304():
    resp1 = FakeResponse()
    await meta(_make_request(), resp1)
    etag = resp1.headers["ETag"]

    resp2 = FakeResponse()
    body = await meta(_make_request({"if-none-match": etag}), resp2)
    assert resp2.status_code == 304
    assert body == {}


@pytest.mark.asyncio
async def test_meta_never_returns_full_key():
    """ETag 改造不破坏脱敏契约：api_key_mask 只能是掩码或空。"""
    payload = await meta(_make_request(), FakeResponse())
    mask = payload.get("api_key_mask")
    assert mask is None or mask == "" or mask.endswith("***")


@pytest.mark.asyncio
async def test_etag_changes_when_payload_changes():
    """不同 payload → 不同 ETag（system vs meta）。"""
    r1 = FakeResponse()
    await system_info(_make_request(), r1)
    e1 = r1.headers["ETag"]
    r2 = FakeResponse()
    await meta(_make_request(), r2)
    e2 = r2.headers["ETag"]
    assert e1 != e2
