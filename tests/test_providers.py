"""多提供商网关单测：注册表 / 模型命名 / 路由分发 / mock 生成链路。"""
import asyncio
import os

import pytest

os.environ.setdefault("IF_ACCOUNT_AUTO", "0")
os.environ.setdefault("IF_MOCK_REGISTER", "1")

from api.providers import registry
from api.providers.registry import bootstrap
from api.providers.base import GenerationResult, ProviderError


@pytest.fixture(autouse=True)
def _bootstrap():
    bootstrap()
    yield


# ── 注册表 / 模型命名 ─────────────────────────────
class TestRegistry:
    def test_providers_registered(self):
        assert set(registry.providers) >= {"imagefree", "minimaxh3", "aifreeforever", "nanobanana"}

    def test_model_naming_contract(self):
        """命名契约：<提供商前缀>/<上游真实模型名>。"""
        specs = registry.all_models()
        assert len(specs) >= 40
        for m in specs:
            assert "/" in m.id, f"模型 id 必须含提供商前缀: {m.id}"
            assert m.id.startswith(m.provider + "/")
            # 上游模型名非空且真实（不含我们的前缀）
            assert m.upstream_model and m.upstream_model not in m.id.split("/")[0]

    def test_minimaxh3_models(self):
        assert "minimaxh3/nano-banana-pro" in registry._models
        assert "minimaxh3/seedance-1.5-pro" in registry._models  # 480P 视频模型（用户指定必支持）
        spec = registry.model("minimaxh3/seedance-1.5-pro")
        assert "txt2vid" in spec.capabilities
        assert "480p" in spec.resolutions

    def test_aifreeforever_models(self):
        assert "aifreeforever/gpt-image-2" in registry._models
        spec = registry.model("aifreeforever/gpt-image-2")
        assert "img2img" in spec.capabilities
        assert "nanobanana/nano-banana-pro" in registry._models

    def test_imagefree_legacy_presets(self):
        assert "imagefree/default" in registry._models
        assert "imagefree/anime" in registry._models

    def test_provider_summary(self):
        s = registry.provider_summary()
        assert s["minimaxh3"]["needs_account"] is True
        assert s["aifreeforever"]["needs_proxy_per_request"] is True
        assert s["nanobanana"]["needs_account"] is True
        assert s["imagefree"]["needs_account"] is False


# ── 提供商 mock 生成 ─────────────────────────────
MOCK_ACC = [{"email": "m@mock.com", "cookie": "mock-session", "credits": 4}]


class TestProviderGenerate:
    @pytest.mark.asyncio
    async def test_imagefree_provider_needs_engine(self):
        p = registry.providers["imagefree"]
        res = await p.generate("imagefree/default", "cat", "1:1")
        assert res.status == "error"  # 引擎未注入 → 明确报错
        assert "未就绪" in res.error

    @pytest.mark.asyncio
    async def test_minimaxh3_mock_account_generates(self, monkeypatch):
        """mock 号池账号（cookie=mock-session）→ 直接返回模拟 completed（确定性 E2E）。"""
        p = registry.providers["minimaxh3"]
        monkeypatch.setattr(p, "_load_accounts", lambda: MOCK_ACC)
        res = await p.generate("minimaxh3/nano-banana-pro", "cat", "1:1", resolution="1K")
        assert res.status == "completed"
        assert res.asset_url and "mock.example" in res.asset_url

    @pytest.mark.asyncio
    async def test_minimaxh3_video_mock(self, monkeypatch):
        p = registry.providers["minimaxh3"]
        monkeypatch.setattr(p, "_load_accounts", lambda: MOCK_ACC)
        res = await p.generate("minimaxh3/seedance-1.5-pro", "v", "16:9", resolution="480p", duration=4)
        assert res.status == "completed"
        assert "mock.example" in res.asset_url

    @pytest.mark.asyncio
    async def test_minimaxh3_no_account_error(self, monkeypatch):
        p = registry.providers["minimaxh3"]
        monkeypatch.setattr(p, "_load_accounts", lambda: [])
        res = await p.generate("minimaxh3/nano-banana-pro", "cat", "1:1")
        assert res.status == "error"
        assert "号池" in res.error

    @pytest.mark.asyncio
    async def test_minimaxh3_exhausted_credits(self, monkeypatch):
        p = registry.providers["minimaxh3"]
        monkeypatch.setattr(p, "_load_accounts", lambda: [dict(MOCK_ACC[0], credits=0)])
        res = await p.generate("minimaxh3/nano-banana-pro", "cat", "1:1")
        assert res.status == "error"
        assert "余额" in res.error

    @pytest.mark.asyncio
    async def test_aifreeforever_no_proxy_pool(self):
        p = registry.providers["aifreeforever"]
        p._proxy_pool = None
        res = await p.generate("aifreeforever/gpt-image-2", "cat", "1:1")
        # 无代理池时回退直连，可能因 cf_solver 不可用而失败
        assert res.status in ("error",)

    @pytest.mark.asyncio
    async def test_nanobanana_contract_placeholder(self):
        p = registry.providers["nanobanana"]
        res = await p.generate("nanobanana/nano-banana-pro", "cat", "1:1")
        assert res.status == "error"  # 契约待确认阶段明确报错，不静默


# ── main 路由分发（mock 全开）────────────────────
@pytest.mark.asyncio
async def test_dispatch_generate_routes(tmp_db, monkeypatch):
    import api.main as m

    # 用临时 DB 隔离
    monkeypatch.setattr(m, "db", tmp_db)
    monkeypatch.setattr(m.engine, "db", tmp_db)
    await m.engine.start()
    try:
        # imagefree → 引擎队列
        tid = await m._dispatch_generate(type("R", (), {"prompt": "x", "aspect_ratio": "1:1",
                                                        "download": False, "model": "imagefree/default",
                                                        "resolution": "1K", "duration": None,
                                                        "priority": None})())
        assert tid and (await tmp_db.get(tid)) is not None

        # minimaxh3 mock 号池 → 后台任务 completed
        prov = m.registry.providers["minimaxh3"]
        monkeypatch.setattr(prov, "_load_accounts", lambda: list(MOCK_ACC))
        tid2 = await m._dispatch_generate(type("R", (), {"prompt": "cat", "aspect_ratio": "1:1",
                                                         "download": False, "model": "minimaxh3/nano-banana-pro",
                                                         "resolution": "1K", "duration": None,
                                                         "priority": None})())
        for _ in range(20):
            if (await tmp_db.get(tid2))["status"] in ("completed", "error"):
                break
            await asyncio.sleep(0.1)
        assert (await tmp_db.get(tid2))["status"] == "completed"
        assert (await tmp_db.get(tid2))["model"] == "minimaxh3/nano-banana-pro"
    finally:
        await m.engine.stop()


@pytest.mark.asyncio
async def test_dispatch_edit_routes(tmp_db, monkeypatch):
    import api.main as m

    monkeypatch.setattr(m, "db", tmp_db)
    monkeypatch.setattr(m.engine, "db", tmp_db)
    await m.engine.start()
    try:
        prov = m.registry.providers["minimaxh3"]
        monkeypatch.setattr(prov, "_load_accounts", lambda: list(MOCK_ACC))
        tid = await m._dispatch_edit("minimaxh3/nano-banana-pro", "make red", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, False)
        for _ in range(20):
            if (await tmp_db.get(tid))["status"] in ("completed", "error"):
                break
            await asyncio.sleep(0.1)
        assert (await tmp_db.get(tid))["status"] == "completed"
        assert (await tmp_db.get(tid))["type"] == "img"
    finally:
        await m.engine.stop()


def test_normalize_model_legacy():
    from api.main import _normalize_model
    assert _normalize_model("default") == "imagefree/default"
    assert _normalize_model("anime") == "imagefree/anime"
    assert _normalize_model("minimaxh3/gpt-image-2") == "minimaxh3/gpt-image-2"
