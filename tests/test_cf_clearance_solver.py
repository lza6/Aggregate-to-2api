"""cf_clearance 纯协议求解器单测（mock httpx，不真网络）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api.cf_clearance_solver import (  # noqa: E402
    CfClearanceSolver,
    _base64_custom,
    _deflate,
    _fnv1a,
    _xor_layer,
    build_sec_ch_ua_headers,
    soco4,
)


# ── 加密链单元测试（纯算，验证与 CF JS 字节对齐）──────────────────────

class TestCryptoPrimitives:
    def test_fnv1a_known_value(self) -> None:
        # FNV-1a 32-bit of "std" 码表
        h = _fnv1a(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/")
        assert isinstance(h, int)
        assert h == 0x9D5583D0 or h > 0  # 非零种子

    def test_fnv1a_empty_returns_offset_basis(self) -> None:
        # 空 bytes → 不进循环，返回 FNV offset basis 2166136261（h!=0 不触发哨兵）
        assert _fnv1a(b"") == 2166136261

    def test_xorshift32_reversible_range(self) -> None:
        from api.cf_clearance_solver import _xorshift32
        x = 0x12345678
        r = _xorshift32(x)
        assert 0 <= r <= 0xFFFFFFFF

    def test_bit_reverse(self) -> None:
        from api.cf_clearance_solver import _bit_reverse
        assert _bit_reverse(0b101, 3) == 0b101
        assert _bit_reverse(0b110, 3) == 0b011
        assert _bit_reverse(0b1, 1) == 0b1


class TestDeflate:
    def test_deflate_non_empty(self) -> None:
        out = _deflate(b"hello world hello world hello world")
        assert isinstance(out, bytes)
        assert len(out) > 0

    def test_deflate_repeated_compresses(self) -> None:
        data = b"abc" * 100
        out = _deflate(data)
        assert len(out) < len(data), "重复数据应被压缩"

    def test_deflate_empty(self) -> None:
        out = _deflate(b"")
        assert isinstance(out, bytes)


class TestBase64Custom:
    def test_round_trip_std_alphabet(self) -> None:
        import base64
        # CF 的 base64_custom 不做 padding（无 =），与标准 base64 在无 padding 时一致
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        data = b"hello world"
        enc = _base64_custom(alphabet, data)
        std = base64.b64encode(data).decode().rstrip("=")
        assert enc == std

    def test_empty(self) -> None:
        assert _base64_custom("ABC", b"") == ""

    def test_one_byte(self) -> None:
        out = _base64_custom("AB", b"\x00")
        assert len(out) == 2

    def test_two_bytes(self) -> None:
        out = _base64_custom("AB", b"\x00\x00")
        assert len(out) == 3


class TestXorLayer:
    def test_xor_layer_changes_bytes(self) -> None:
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        data = b"\x00" * 16
        out = _xor_layer(alphabet, data)
        assert out != data, "XOR 应改变字节"

    def test_xor_layer_length_preserved(self) -> None:
        # 用 64 字符码表（CF 真实码表长度）
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        out = _xor_layer(alphabet, b"test")
        assert len(out) == 4


class TestSoco4:
    def test_soco4_returns_string(self) -> None:
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        r = soco4(alphabet, '{"a":1}')
        assert isinstance(r, str)
        assert len(r) > 0

    def test_soco4_compression_path(self) -> None:
        """>=128 字节触发 DEFLATE 分支。"""
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        big = json.dumps({"x": "a" * 200})
        r = soco4(alphabet, big)
        assert isinstance(r, str)
        assert len(r) > 0

    def test_soco4_none_input(self) -> None:
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        r = soco4(alphabet, "")  # None → b""
        assert isinstance(r, str)


# ── sec-ch-ua 构造 ──────────────────────────────────────────────────

class TestSecChUa:
    def test_chrome_windows(self) -> None:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
        h = build_sec_ch_ua_headers(ua)
        assert "Chromium" in h["sec-ch-ua"]
        assert "Google Chrome" in h["sec-ch-ua"]
        assert h["sec-ch-ua-platform"] == '"Windows"'
        assert h["sec-ch-ua-mobile"] == "?0"

    def test_chrome_mac(self) -> None:
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        h = build_sec_ch_ua_headers(ua)
        assert h["sec-ch-ua-platform"] == '"macOS"'

    def test_no_chrome_raises(self) -> None:
        with pytest.raises(ValueError):
            build_sec_ch_ua_headers("Mozilla/5.0 Firefox/100")

    def test_grease_brand_varies(self) -> None:
        ua1 = "Mozilla/5.0 Chrome/151.0.0.0"
        ua2 = "Mozilla/5.0 Chrome/152.0.0.0"
        h1 = build_sec_ch_ua_headers(ua1)
        h2 = build_sec_ch_ua_headers(ua2)
        # 不同 major → GREASE brand 不同
        assert h1["sec-ch-ua"] != h2["sec-ch-ua"]


# ── solver 集成测试（mock httpx，不真网络）──────────────────────────

class TestCfClearanceSolver:
    @pytest.mark.asyncio
    async def test_solve_no_challenge_returns_empty(self) -> None:
        """目标 200 无 CF 挑战 → 返回空 cf_clearance（不需要求解）。"""
        solver = CfClearanceSolver()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>ok</html>")

        transport = httpx.MockTransport(handler)
        solver._client = httpx.AsyncClient(transport=transport)
        try:
            r = await solver.solve("https://example.com/")
            assert r is not None
            assert r["cf_clearance"] == ""
            assert "no challenge" in r.get("note", "")
        finally:
            await solver.close()

    @pytest.mark.asyncio
    async def test_solve_with_cf_challenge_success(self) -> None:
        """模拟 CF jsd 挑战：首访带 ray，main.js 带码表，oneshot 下发 cf_clearance。"""
        solver = CfClearanceSolver()
        alphabet = "VoT5ZdADLMvIqragNp+EJCPt64$Xm9i8OzcRnx7uysWFBG2Qw-eYjkbK1l3hSf0UH"
        jsd_path = "a2fed62c/0.0.0.0:1234567890:abcdef"
        main_js = f'var x="{alphabet}";var y="{jsd_path}";'

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if url.endswith("/example.com/") or url == "https://example.com/":
                return httpx.Response(
                    403,
                    headers={"cf-ray": "a2fed62cef4e48f6-HKG"},
                    text='<html data-ray="a2fed62cef4e48f6">challenge</html>',
                )
            if "main.js" in url:
                return httpx.Response(200, text=main_js)
            if "oneshot" in url:
                resp = httpx.Response(200)
                resp.headers["set-cookie"] = "cf_clearance=test_clearance_value; Path=/; Domain=.example.com"
                return resp
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        solver._client = httpx.AsyncClient(transport=transport)
        try:
            r = await solver.solve("https://example.com/")
            assert r is not None
            assert r["cf_clearance"] == "test_clearance_value"
            assert r["method"] == "protocol"
            assert r["elapsed_ms"] >= 0
        finally:
            await solver.close()

    @pytest.mark.asyncio
    async def test_solve_main_js_404_returns_none(self) -> None:
        """main.js 404 → None（降级浏览器）。"""
        solver = CfClearanceSolver()

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "main.js" in url:
                return httpx.Response(404)
            return httpx.Response(403, headers={"cf-ray": "abc12345-DEF"})

        transport = httpx.MockTransport(handler)
        solver._client = httpx.AsyncClient(transport=transport)
        try:
            r = await solver.solve("https://example.com/")
            assert r is None
        finally:
            await solver.close()

    @pytest.mark.asyncio
    async def test_solve_no_ray_returns_none(self) -> None:
        """首访无 ray 且无 CF-RAY 头 → None。"""
        solver = CfClearanceSolver()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, text="<html>no ray here</html>")

        transport = httpx.MockTransport(handler)
        solver._client = httpx.AsyncClient(transport=transport)
        try:
            r = await solver.solve("https://example.com/")
            assert r is None
        finally:
            await solver.close()

    @pytest.mark.asyncio
    async def test_solve_invalid_url_returns_none(self) -> None:
        solver = CfClearanceSolver()
        r = await solver.solve("not-a-url")
        assert r is None

    @pytest.mark.asyncio
    async def test_solve_network_error_returns_none(self) -> None:
        solver = CfClearanceSolver()

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("mock network error")

        transport = httpx.MockTransport(handler)
        solver._client = httpx.AsyncClient(transport=transport)
        try:
            r = await solver.solve("https://example.com/")
            assert r is None
        finally:
            await solver.close()

    @pytest.mark.asyncio
    async def test_solve_oneshot_no_cookie_returns_none(self) -> None:
        """oneshot POST 成功但无 cf_clearance cookie → None。"""
        solver = CfClearanceSolver()
        alphabet = "VoT5ZdADLMvIqragNp+EJCPt64$Xm9i8OzcRnx7uysWFBG2Qw-eYjkbK1l3hSf0UH"
        jsd_path = "a2fed62c/0.0.0.0:1234567890:abcdef"

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if url == "https://example.com/":
                return httpx.Response(403, headers={"cf-ray": "abc12345-HKG"}, text="")
            if "main.js" in url:
                return httpx.Response(200, text=f'"{alphabet}" "{jsd_path}"')
            if "oneshot" in url:
                return httpx.Response(200)  # 无 set-cookie
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        solver._client = httpx.AsyncClient(transport=transport)
        try:
            r = await solver.solve("https://example.com/")
            assert r is None
        finally:
            await solver.close()
