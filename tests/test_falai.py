"""fal.ai Provider 纯算版单测（mock httpx + mock bootstrap，不真网络不真浏览器）。"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api.providers.falai import (  # noqa: E402
    FalaiProvider,
    FalaiSession,
    _KasadaSigner,
)

# ── Kasada 纯算签名 ────────────────────────────────────────────────

class TestKasadaSigner:
    def test_sign_returns_base64_string(self) -> None:
        signer = _KasadaSigner()
        s = signer.sign()
        assert isinstance(s, str)
        assert len(s) > 20
        # 验证是合法 base64
        raw = base64.b64decode(s)
        assert len(raw) > 16  # ct + 16 字节 tag

    def test_sign_different_each_call(self) -> None:
        signer = _KasadaSigner()
        s1 = signer.sign()
        s2 = signer.sign()
        # iv 随机 → 每次不同
        assert s1 != s2

    def test_key_cached(self) -> None:
        signer = _KasadaSigner()
        signer._ensure_key()
        key1 = signer._aes_key
        signer._ensure_key()
        key2 = signer._aes_key
        assert key1 is key2  # 同一对象引用，未重新派生

    def test_build_x_is_human_structure(self) -> None:
        signer = _KasadaSigner()
        e = "test_e_blob"
        xih = signer.build_x_is_human(e)
        obj = json.loads(xih)
        assert obj["b"] == 0
        assert obj["v"] == 0.209
        assert obj["e"] == "test_e_blob"
        assert "s" in obj and len(obj["s"]) > 20
        assert obj["d"] == 0
        assert obj["vr"] == "3"


# ── FalaiSession ──────────────────────────────────────────────────

class TestFalaiSession:
    def test_is_valid_empty(self) -> None:
        s = FalaiSession()
        assert not s.is_valid()

    def test_is_valid_with_data(self) -> None:
        s = FalaiSession(
            fal_free="free",
            fal_free_id="id",
            host_csrf="csrf",
            e_blob="e",
            acquired_at=__import__("time").time(),
        )
        assert s.is_valid()

    def test_is_valid_expired(self) -> None:
        import time
        s = FalaiSession(
            fal_free="free",
            host_csrf="csrf",
            e_blob="e",
            acquired_at=time.time() - 90000,  # 25h 前
        )
        assert not s.is_valid()

    def test_can_use_under_limit(self) -> None:
        import time
        s = FalaiSession(
            fal_free="free",
            host_csrf="csrf",
            e_blob="e",
            acquired_at=time.time(),
            daily_reset_at=time.time() + 86400,
        )
        assert s.can_use(5)
        s.use_count = 5
        assert not s.can_use(5)

    def test_can_use_resets_daily(self) -> None:
        import time
        s = FalaiSession(
            fal_free="free",
            host_csrf="csrf",
            e_blob="e",
            acquired_at=time.time(),
            use_count=5,
            daily_reset_at=time.time() - 1,  # 已过期 → 重置
        )
        assert s.can_use(5)  # 重置后 use_count=0


# ── FalaiProvider 模型注册 ────────────────────────────────────────

class TestFalaiProviderModels:
    def test_models_registered(self) -> None:
        p = FalaiProvider()
        assert "falai/minimax-h3-max-txt" in p.models
        assert "falai/minimax-h3-max-img" in p.models

    def test_needs_proxy_per_request(self) -> None:
        p = FalaiProvider()
        assert p.needs_proxy_per_request() is True

    def test_capabilities(self) -> None:
        p = FalaiProvider()
        from api.providers.base import CAP_IMG2VID, CAP_TXT2VID
        txt = p.models["falai/minimax-h3-max-txt"]
        assert CAP_TXT2VID in txt.capabilities
        img = p.models["falai/minimax-h3-max-img"]
        assert CAP_IMG2VID in img.capabilities


# ── Provider generate（mock httpx + mock session）─────────────────

class TestFalaiProviderGenerate:
    @pytest.mark.asyncio
    async def test_generate_no_session_returns_error(self) -> None:
        p = FalaiProvider()
        # mock _get_session 返回 None（无 bootstrap）
        p._get_session = AsyncMock(return_value=None)
        r = await p.generate("falai/minimax-h3-max-txt", "cat", "16:9")
        assert r.status == "error"
        assert "会话不可用" in r.error

    @pytest.mark.asyncio
    async def test_generate_unknown_model(self) -> None:
        p = FalaiProvider()
        r = await p.generate("falai/unknown", "cat", "16:9")
        assert r.status == "error"
        assert "未知模型" in r.error

    @pytest.mark.asyncio
    async def test_generate_txt2vid_success(self) -> None:
        """mock 完整链路：submit→poll→result。"""
        import time
        p = FalaiProvider()
        sess = FalaiSession(
            fal_free="free",
            fal_free_id="id",
            host_csrf="csrf",
            e_blob="e_blob",
            acquired_at=time.time(),
        )
        p._get_session = AsyncMock(return_value=sess)
        p._proxy_pool = MagicMock()
        p._proxy_pool.acquire = AsyncMock(return_value=None)
        p._proxy_pool.mark_success = AsyncMock()
        # mock 各步骤
        p._submit = AsyncMock(return_value="req-123")
        p._poll = AsyncMock(return_value="COMPLETED")
        p._fetch_result = AsyncMock(return_value="https://v3b.fal.media/test.mp4")
        r = await p.generate("falai/minimax-h3-max-txt", "a cat", "16:9")
        assert r.status == "completed"
        assert r.asset_url == "https://v3b.fal.media/test.mp4"
        p._submit.assert_called_once()
        p._poll.assert_called_once()
        p._fetch_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_img2vid_with_upload(self) -> None:
        import time
        p = FalaiProvider()
        sess = FalaiSession(
            fal_free="free",
            host_csrf="csrf",
            e_blob="e_blob",
            acquired_at=time.time(),
        )
        p._get_session = AsyncMock(return_value=sess)
        p._proxy_pool = MagicMock()
        p._proxy_pool.acquire = AsyncMock(return_value=None)
        p._proxy_pool.mark_success = AsyncMock()
        p._upload_image = AsyncMock(return_value="https://v3b.fal.media/img.png")
        p._submit = AsyncMock(return_value="req-456")
        p._poll = AsyncMock(return_value="COMPLETED")
        p._fetch_result = AsyncMock(return_value="https://v3b.fal.media/video.mp4")
        r = await p.generate(
            "falai/minimax-h3-max-img", "a cat", "16:9", images=[b"fakeimg"]
        )
        assert r.status == "completed"
        p._upload_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_poll_timeout(self) -> None:
        import time
        p = FalaiProvider()
        sess = FalaiSession(
            fal_free="free",
            host_csrf="csrf",
            e_blob="e_blob",
            acquired_at=time.time(),
        )
        p._get_session = AsyncMock(return_value=sess)
        p._proxy_pool = MagicMock()
        p._proxy_pool.acquire = AsyncMock(return_value=None)
        p._submit = AsyncMock(return_value="req-789")
        p._poll = AsyncMock(return_value="TIMEOUT")
        r = await p.generate("falai/minimax-h3-max-txt", "cat", "16:9")
        assert r.status == "error"
        assert "TIMEOUT" in r.error

    @pytest.mark.asyncio
    async def test_generate_no_request_id(self) -> None:
        import time
        p = FalaiProvider()
        sess = FalaiSession(
            fal_free="free",
            host_csrf="csrf",
            e_blob="e_blob",
            acquired_at=time.time(),
        )
        p._get_session = AsyncMock(return_value=sess)
        p._proxy_pool = MagicMock()
        p._proxy_pool.acquire = AsyncMock(return_value=None)
        p._submit = AsyncMock(return_value=None)
        r = await p.generate("falai/minimax-h3-max-txt", "cat", "16:9")
        assert r.status == "error"
        assert "request_id" in r.error

    @pytest.mark.asyncio
    async def test_generate_rate_limited(self) -> None:
        import time

        from api.providers.base import ProviderRateLimited
        p = FalaiProvider()
        sess = FalaiSession(
            fal_free="free",
            host_csrf="csrf",
            e_blob="e_blob",
            acquired_at=time.time(),
        )
        p._get_session = AsyncMock(return_value=sess)
        p._proxy_pool = MagicMock()
        p._proxy_pool.acquire = AsyncMock(return_value="http://proxy:8080")
        p._proxy_pool.mark_failure = AsyncMock()
        p._submit = AsyncMock(side_effect=ProviderRateLimited("限流"))
        r = await p.generate("falai/minimax-h3-max-txt", "cat", "16:9")
        assert r.status == "error"
        assert "限流" in r.error
        p._proxy_pool.mark_failure.assert_called_once()


# ── headers 构造（含纯算 x-is-human）─────────────────────────────

class TestHeaders:
    def test_headers_contain_x_is_human(self) -> None:
        import time
        p = FalaiProvider()
        sess = FalaiSession(
            fal_free="free",
            host_csrf="csrf_token",
            e_blob="e_blob_value",
            acquired_at=time.time(),
        )
        h = p._headers(sess, "POST", "https://queue.fal.run/test")
        assert "x-is-human" in h
        assert "x-csrf-token" in h
        assert h["x-csrf-token"] == "csrf_token"
        assert h["x-fal-target-url"] == "https://queue.fal.run/test"
        assert h["x-method"] == "POST"
        assert h["x-fal-queue-priority"] == "normal"
        # x-is-human 是合法 JSON
        obj = json.loads(h["x-is-human"])
        assert obj["e"] == "e_blob_value"

    def test_headers_get_no_queue_priority(self) -> None:
        import time
        p = FalaiProvider()
        sess = FalaiSession(
            fal_free="free",
            host_csrf="csrf",
            e_blob="e",
            acquired_at=time.time(),
        )
        h = p._headers(sess, "GET", "https://test")
        assert "x-fal-queue-priority" not in h

    def test_cookies(self) -> None:
        import time
        p = FalaiProvider()
        sess = FalaiSession(
            fal_free="free_val",
            fal_free_id="id_val",
            host_csrf="csrf_val",
            e_blob="e",
            acquired_at=time.time(),
        )
        c = p._cookies(sess)
        assert c["__fal_free"] == "free_val"
        assert c["__fal_free_id"] == "id_val"
        assert c["__Host-csrf"] == "csrf_val"
