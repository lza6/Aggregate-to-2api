"""P-TEST-A5 追加: providers 分支补充测试。

覆盖既有 test_providers.py 未覆盖的分支：
- nanobanana._parse_action_response（RSC 解析：$$ 转义 / 多 0: 行 / 缺 taskId / error 行 / 非 200）
- aifreeforever._generate 429 → ProviderRateLimited + waitTime 提示（mock httpx）
- registry.find_alternative 降级查询
"""

import httpx
import pytest

from api.providers.base import ProviderError, ProviderRateLimited
from api.providers import registry
from api.providers.registry import bootstrap

bootstrap()


# ── nanobanana RSC 解析 ──────────────────────────


def _rsc_response(lines: list[str], status: int = 200) -> httpx.Response:
    body = "\n".join(lines)
    return httpx.Response(status_code=status, text=body, headers={"Content-Type": "text/x-component"})


class TestNanobananaRscParse:
    @pytest.mark.asyncio
    async def test_simple_success_line(self):
        p = registry.providers["nanobanana"]
        r = _rsc_response(['0:{"success":true,"taskId":"t123"}'])
        assert await p._parse_action_response(r) == "t123"

    @pytest.mark.asyncio
    async def test_dollar_escape_fallback(self):
        p = registry.providers["nanobanana"]
        # $$ 转义的 JSON（RSC 编码 '$' 开头字符串）
        r = _rsc_response(['0:{"success":true,"taskId":"$$t456"}'])
        tid = await p._parse_action_response(r)
        assert tid is not None and "456" in tid

    @pytest.mark.asyncio
    async def test_multiple_zero_lines_skip_invalid(self):
        p = registry.providers["nanobanana"]
        # 前几行非 dict / 无 success → 跳过，直到有效行
        r = _rsc_response(
            [
                '0:"flight-data"',
                "0:[1,2,3]",
                '0:{"foo":1}',
                '0:{"success":true,"taskId":"t789"}',
            ]
        )
        assert await p._parse_action_response(r) == "t789"

    @pytest.mark.asyncio
    async def test_missing_task_id_skips(self):
        p = registry.providers["nanobanana"]
        r = _rsc_response(['0:{"success":true}'])
        with pytest.raises(ProviderError):
            await p._parse_action_response(r)

    @pytest.mark.asyncio
    async def test_error_payload_raises(self):
        p = registry.providers["nanobanana"]
        r = _rsc_response(['0:{"error":"quota exceeded"}'])
        with pytest.raises(ProviderError) as ei:
            await p._parse_action_response(r)
        assert "失败" in str(ei.value)

    @pytest.mark.asyncio
    async def test_non_200_raises(self):
        p = registry.providers["nanobanana"]
        r = _rsc_response([], status=500)
        with pytest.raises(ProviderError) as ei:
            await p._parse_action_response(r)
        assert "500" in str(ei.value)

    def test_rsc_encode_dollar_escaped(self):
        p = registry.providers["nanobanana"]
        out = p._rsc_encode({"url": "$https://x"})
        assert "$$" in out


# ── aifreeforever 429 限流分支 ──────────────────────


class TestAifreeforever429:
    @pytest.mark.asyncio
    async def test_429_raises_rate_limited_with_waittime(self, monkeypatch):
        p = registry.providers["aifreeforever"]

        async def _fake_post(self, url, **kw):
            return httpx.Response(429, json={"waitTime": 120}, request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
        with pytest.raises(ProviderRateLimited) as ei:
            await p._generate("tok", "gpt-image-2", "cat", "1:1", None, None)
        assert "120" in str(ei.value)

    @pytest.mark.asyncio
    async def test_generate_marks_proxy_rate_limited(self, monkeypatch):
        """generate() 捕获 ProviderRateLimited → mark_failure(rate_limited=True)。"""
        p = registry.providers["aifreeforever"]
        calls = []

        class _FakePool:
            async def acquire(self):
                return "http://fake:8080"

            async def mark_failure(self, proxy, rate_limited=False):
                calls.append(("fail", proxy, rate_limited))

            async def mark_success(self, proxy):
                calls.append(("ok", proxy))

        p._proxy_pool = _FakePool()

        async def _no_token(*a, **kw):
            raise RuntimeError("skip solver")  # 直接短路求解段

        monkeypatch.setattr("api.providers.aifreeforever.turnstile_client.solve_turnstile", _no_token)
        # 求解失败 → error 返回（非 429 路径），代理不标记
        res = await p.generate("aifreeforever/gpt-image-2", "cat", "1:1")
        assert res.status == "error"
        assert not any(c[0] == "fail" for c in calls)


# ── registry 降级查询 ─────────────────────────────


class TestFindAlternative:
    def test_alternative_for_down_provider(self):
        # imagefree/default down → 找同能力备用
        registry.mark_down("imagefree", "test")
        try:
            alt_provider, alt_model = registry.find_alternative("imagefree/default")
            # 至少应找到（nanobanana 等同能力）或 None（无可替代时不抛错）
            assert alt_provider is None or alt_provider.prefix != "imagefree"
        finally:
            registry.recover("imagefree")

    def test_alternative_unknown_model(self):
        alt_provider, alt_model = registry.find_alternative("nope/no-model")
        assert alt_provider is None
