"""api/providers/aifreeforever.py 内部方法单元测试（P0-2 续，mock httpx 不发真实请求）。

覆盖：_headers（带/不带 token）、_moderate（pass/非 pass/异常）、_generate
（单图/多图/非200/非JSON/429/失败响应/空 images）、_download（成功/HTTP 错误）。
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.providers import aifreeforever as aff
from api.providers.aifreeforever import AifreeforeverProvider
from api.providers.base import ProviderError, ProviderRateLimited


@pytest.fixture
def provider() -> AifreeforeverProvider:
    return AifreeforeverProvider()


# ── _headers ─────────────────────────────────────────────────


def test_headers_without_token(provider):
    h = provider._headers()
    assert h["Origin"] == provider.base_url
    assert h["Referer"].endswith("/image-generators")
    assert h["x-api-secret"] == ""
    assert "x-captcha-verified-at" not in h
    assert "x-turnstile-token" not in h
    assert h["User-Agent"].startswith("Mozilla/5.0")


def test_headers_with_token(provider):
    h = provider._headers("tok123")
    assert "x-captcha-verified-at" in h  # 毫秒时间戳
    assert h["x-turnstile-token"] == "tok123"


def test_headers_does_not_mutate_class_constant(provider):
    original = dict(aff._BROWSER_HEADERS)
    provider._headers("tok")
    provider._headers()
    assert original == aff._BROWSER_HEADERS  # 类常量不被污染


# ── _generate ────────────────────────────────────────────────


def _mock_client(json_data=None, status=200, raw=b"", capture: dict | None = None):
    """构造 mock AsyncClient：post 捕获 kwargs 到 capture（可选）并返回 resp。"""
    client = MagicMock()
    resp = MagicMock()
    resp.status_code = status
    resp.text = raw.decode() if raw else ""
    if json_data is not None:
        resp.json = MagicMock(return_value=json_data)
    else:
        resp.json = MagicMock(side_effect=ValueError("not json"))
    client.resp = resp

    async def _post(url, **kw):
        if capture is not None:
            capture.update(kw)
        return resp

    client.post = _post
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
async def test_generate_success_no_images(provider, monkeypatch):
    monkeypatch.setattr(aff.httpx, "AsyncClient", MagicMock(return_value=_mock_client({"success": True, "images": ["u1", "u2"]})))
    urls = await provider._generate("tok", "seedream-4", "cat", "1:1", None, None)
    assert urls == ["u1", "u2"]


@pytest.mark.asyncio
async def test_generate_single_image_reference(provider, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        aff.httpx, "AsyncClient",
        MagicMock(return_value=_mock_client({"success": True, "images": []}, capture=captured)),
    )
    img = b"\x89PNG"
    await provider._generate("tok", "m", "p", "1:1", [img], None)
    body = captured["json"]
    assert body["referenceImageUrl"].startswith("data:image/png;base64,")
    assert base64.b64decode(body["referenceImageUrl"].split(",", 1)[1]) == img


@pytest.mark.asyncio
async def test_generate_multi_image_references(provider, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        aff.httpx, "AsyncClient",
        MagicMock(return_value=_mock_client({"success": True, "images": []}, capture=captured)),
    )
    imgs = [b"a", b"b", b"c"]
    await provider._generate("tok", "m", "p", "1:1", imgs, None)
    body = captured["json"]
    assert "referenceImageUrls" in body
    assert len(body["referenceImageUrls"]) == 3


@pytest.mark.asyncio
async def test_generate_more_than_3_images_clamped(provider, monkeypatch):
    """>3 张参考图钳到 3 张。"""
    captured: dict = {}
    monkeypatch.setattr(
        aff.httpx, "AsyncClient",
        MagicMock(return_value=_mock_client({"success": True, "images": []}, capture=captured)),
    )
    imgs = [b"a", b"b", b"c", b"d", b"e"]
    await provider._generate("tok", "m", "p", "1:1", imgs, None)
    assert len(captured["json"]["referenceImageUrls"]) == 3


@pytest.mark.asyncio
async def test_generate_non_json_raises_provider_error(provider, monkeypatch):
    monkeypatch.setattr(aff.httpx, "AsyncClient", MagicMock(return_value=_mock_client(None, status=502, raw=b"bad gateway")))
    with pytest.raises(ProviderError, match="生成失败"):
        await provider._generate("tok", "m", "p", "1:1", None, None)


@pytest.mark.asyncio
async def test_generate_429_raises_rate_limited(provider, monkeypatch):
    monkeypatch.setattr(
        aff.httpx, "AsyncClient",
        MagicMock(return_value=_mock_client({"success": False, "waitTime": 120}, status=429)),
    )
    with pytest.raises(ProviderRateLimited, match="120"):
        await provider._generate("tok", "m", "p", "1:1", None, None)


@pytest.mark.asyncio
async def test_generate_429_default_wait(provider, monkeypatch):
    monkeypatch.setattr(
        aff.httpx, "AsyncClient",
        MagicMock(return_value=_mock_client({"success": False}, status=429)),
    )
    with pytest.raises(ProviderRateLimited, match="60"):
        await provider._generate("tok", "m", "p", "1:1", None, None)


@pytest.mark.asyncio
async def test_generate_success_false_raises(provider, monkeypatch):
    monkeypatch.setattr(
        aff.httpx, "AsyncClient",
        MagicMock(return_value=_mock_client({"success": False, "error": "bad prompt"}, status=200)),
    )
    with pytest.raises(ProviderError, match="bad prompt|生成失败"):
        await provider._generate("tok", "m", "p", "1:1", None, None)


@pytest.mark.asyncio
async def test_generate_empty_images_list_ok(provider, monkeypatch):
    monkeypatch.setattr(
        aff.httpx, "AsyncClient",
        MagicMock(return_value=_mock_client({"success": True, "images": []})),
    )
    assert await provider._generate("tok", "m", "p", "1:1", None, None) == []


# ── _moderate ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_moderate_pass(provider, monkeypatch):
    monkeypatch.setattr(aff.httpx, "AsyncClient", MagicMock(return_value=_mock_client({"result": "pass"})))
    assert await provider._moderate(b"img", None) is True


@pytest.mark.asyncio
async def test_moderate_not_pass(provider, monkeypatch):
    monkeypatch.setattr(aff.httpx, "AsyncClient", MagicMock(return_value=_mock_client({"result": "blocked"})))
    assert await provider._moderate(b"img", None) is False


@pytest.mark.asyncio
async def test_moderate_exception_propagates_or_false(provider, monkeypatch):
    """moderate 网络异常：httpx 层抛出（调用方容错）。"""
    client = MagicMock()
    resp = MagicMock()
    resp.json = MagicMock(side_effect=ConnectionError("down"))
    client.post = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(aff.httpx, "AsyncClient", MagicMock(return_value=client))
    with pytest.raises(ConnectionError):
        await provider._moderate(b"img", None)


# ── _download ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_success(provider, monkeypatch):
    client = MagicMock()
    resp = MagicMock()
    resp.content = b"\x89PNGDATA"
    resp.raise_for_status = MagicMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(aff.httpx, "AsyncClient", MagicMock(return_value=client))
    assert await provider._download("https://img/u.png", None) == b"\x89PNGDATA"


@pytest.mark.asyncio
async def test_download_http_error_raises(provider, monkeypatch):
    client = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock(side_effect=aff.httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock()))
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(aff.httpx, "AsyncClient", MagicMock(return_value=client))
    with pytest.raises(aff.httpx.HTTPStatusError):
        await provider._download("https://img/u.png", None)


# ── needs_proxy_per_request ─────────────────────────────────


def test_needs_proxy_per_request_true(provider):
    assert provider.needs_proxy_per_request() is True  # 是方法不是属性
