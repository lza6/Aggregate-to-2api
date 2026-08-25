"""多提供商网关单测：注册表 / 模型命名 / 路由分发 / mock 生成链路。"""
import asyncio
import os

import pytest

os.environ.setdefault("IF_ACCOUNT_AUTO", "0")
os.environ.setdefault("IF_MOCK_REGISTER", "1")

from api.providers import registry
from api.providers.registry import bootstrap
from api.providers.base import GenerationResult, ProviderError
from api.meta import engine


@pytest.fixture(autouse=True)
def _bootstrap():
    bootstrap()
    yield


# ── 注册表 / 模型命名 ─────────────────────────────
class TestRegistry:
    def test_providers_registered(self):
        assert {"imagefree", "aifreeforever", "nanobanana"} <= set(registry.providers)

    def test_model_naming_contract(self):
        """命名契约：<提供商前缀>/<上游真实模型名>。"""
        specs = registry.all_models()
        assert len(specs) >= 30
        for m in specs:
            assert "/" in m.id, f"模型 id 必须含提供商前缀: {m.id}"
            assert m.id.startswith(m.provider + "/")
            # 上游模型名非空且真实（不含我们的前缀）
            assert m.upstream_model and m.upstream_model not in m.id.split("/")[0]

    def test_nanobanana_models(self):
        assert "nanobanana/nano-banana-pro" in registry._models

    def test_imagefree_legacy_presets(self):
        assert "imagefree/default" in registry._models
        assert "imagefree/anime" in registry._models

    def test_provider_summary(self):
        s = registry.provider_summary()
        assert set(s) >= {"imagefree", "aifreeforever", "nanobanana"}
        assert s["aifreeforever"]["needs_proxy_per_request"] is True
        assert s["nanobanana"]["needs_account"] is True
        assert s["imagefree"]["needs_account"] is False


# ── 提供商 mock 生成 ─────────────────────────────
MOCK_ACC = [{"email": "m@mock.com", "cookie": "mock-session", "credits": 4}]


class TestProviderGenerate:
    @pytest.mark.asyncio
    async def test_imagefree_provider_needsengine(self):
        p = registry.providers["imagefree"]
        res = await p.generate("imagefree/default", "cat", "1:1")
        assert res.status == "error"  # 引擎未注入 → 明确报错
        assert "未就绪" in res.error

    @pytest.mark.asyncio
    async def test_nanobanana_mock_account_generates(self, monkeypatch):
        """mock 号池账号（cookie=mock-session）→ 需先 startup 注入 _client 再回 mock completed。"""
        p = registry.providers["nanobanana"]
        monkeypatch.setattr(p, "_load_accounts", lambda: MOCK_ACC)
        await p.startup()
        res = await p.generate("nanobanana/nano-banana-pro", "cat", "1:1", resolution="1K")
        await p.shutdown()
        assert res.status == "completed"
        assert res.asset_url and "mock.example" in res.asset_url

    @pytest.mark.asyncio
    async def test_nanobanana_no_account_error(self, monkeypatch):
        p = registry.providers["nanobanana"]
        monkeypatch.setattr(p, "_load_accounts", lambda: [])
        await p.startup()
        res = await p.generate("nanobanana/nano-banana-pro", "cat", "1:1")
        await p.shutdown()
        assert res.status == "error"
        assert "号池" in res.error

    @pytest.mark.asyncio
    async def test_nanobanana_exhausted_credits(self, monkeypatch):
        p = registry.providers["nanobanana"]
        monkeypatch.setattr(p, "_load_accounts", lambda: [dict(MOCK_ACC[0], credits=0)])
        await p.startup()
        res = await p.generate("nanobanana/nano-banana-pro", "cat", "1:1")
        await p.shutdown()
        assert res.status == "error"
        assert "余额" in res.error

    @pytest.mark.asyncio
    async def test_aifreeforever_no_proxy_pool(self, monkeypatch):
        p = registry.providers["aifreeforever"]
        # monkeypatch 恢复原值——直接赋 None 会污染全局 registry 单例，
        # 导致后续文件（如 test_account_pool 的无代理守卫用例）拿到 None 池
        monkeypatch.setattr(p, "_proxy_pool", None)
        res = await p.generate("aifreeforever/gpt-image-2", "cat", "1:1")
        # 无代理池时回退直连，可能因 cf_solver 不可用而失败
        assert res.status in ("error",)

    @pytest.mark.asyncio
    async def test_nanobanana_contract_placeholder(self):
        p = registry.providers["nanobanana"]
        res = await p.generate("nanobanana/nano-banana-pro", "cat", "1:1")
        assert res.status == "error"  # 未 startup（_client 为 None）→ 明确报错
        assert "未启动" in res.error


# ── main 路由分发（mock 全开，需 Engine 启动）────────────────────
@pytest.mark.slow
@pytest.mark.asyncio
async def test_dispatch_generate_routes(tmp_db, monkeypatch):
    from api.dispatch import _dispatch_generate

    # 用临时 DB 隔离：dispatch 与 engine 的 db 单例均指向 tmp_db
    monkeypatch.setattr("api.dispatch.db", tmp_db)
    engine.db = tmp_db
    await engine.start()
    try:
        # imagefree → 引擎队列
        tid = await _dispatch_generate(type("R", (), {"prompt": "x", "aspect_ratio": "1:1",
                                                      "download": False, "model": "imagefree/default",
                                                      "resolution": "1K", "duration": None,
                                                      "priority": None})())
        assert tid and (await tmp_db.get(tid)) is not None

        # nanobanana mock 号池 → 后台任务 completed
        prov = registry.providers["nanobanana"]
        monkeypatch.setattr(prov, "_load_accounts", lambda: list(MOCK_ACC))
        await prov.startup()
        tid2 = await _dispatch_generate(type("R", (), {"prompt": "cat", "aspect_ratio": "1:1",
                                                       "download": False, "model": "nanobanana/nano-banana-pro",
                                                       "resolution": "1K", "duration": None,
                                                       "priority": None})())
        for _ in range(20):
            if (await tmp_db.get(tid2))["status"] in ("completed", "error"):
                break
            await asyncio.sleep(0.1)
        await prov.shutdown()
        assert (await tmp_db.get(tid2))["status"] == "completed"
        assert (await tmp_db.get(tid2))["model"] == "nanobanana/nano-banana-pro"
    finally:
        await engine.stop()


@pytest.mark.slow
@pytest.mark.asyncio
async def test_dispatch_edit_routes(tmp_db, monkeypatch):
    from api.dispatch_edit import _dispatch_edit

    monkeypatch.setattr("api.dispatch_edit.db", tmp_db)
    engine.db = tmp_db
    await engine.start()
    try:
        prov = registry.providers["nanobanana"]
        monkeypatch.setattr(prov, "_load_accounts", lambda: list(MOCK_ACC))
        await prov.startup()
        tid = await _dispatch_edit("nanobanana/nano-banana-pro", "make red", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, False)
        for _ in range(20):
            if (await tmp_db.get(tid))["status"] in ("completed", "error"):
                break
            await asyncio.sleep(0.1)
        await prov.shutdown()
        assert (await tmp_db.get(tid))["status"] == "completed"
        assert (await tmp_db.get(tid))["type"] == "img"
    finally:
        await engine.stop()


def test_normalize_model_legacy():
    from api.dispatch import _normalize_model
    assert _normalize_model("default") == "imagefree/default"
    assert _normalize_model("anime") == "imagefree/anime"
    assert _normalize_model("minimaxh3/gpt-image-2") == "minimaxh3/gpt-image-2"
