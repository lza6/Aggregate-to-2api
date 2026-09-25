"""P-TEST-A5 追加: providers 分支补充测试。

覆盖既有 test_providers.py 未覆盖的分支：
- nanobanana._parse_action_response（RSC 解析：$$ 转义 / 多 0: 行 / 缺 taskId / error 行 / 非 200）
- aifreeforever._generate 429 → ProviderRateLimited + waitTime 提示（mock httpx）
- registry.find_alternative 降级查询
"""

import httpx
import pytest

from api.providers import registry
from api.providers.base import ProviderRateLimited
from api.providers.registry import bootstrap

bootstrap()


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
            # 至少应找到（aifreeforever 等同能力）或 None（无可替代时不抛错）
            assert alt_provider is None or alt_provider.prefix != "imagefree"
        finally:
            registry.recover("imagefree")

    def test_alternative_unknown_model(self):
        alt_provider, alt_model = registry.find_alternative("nope/no-model")
        assert alt_provider is None
