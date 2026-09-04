"""多提供商网关单测：注册表 / 模型命名 / 路由分发 / mock 生成链路。"""

import asyncio
import os

import pytest

os.environ.setdefault("IF_ACCOUNT_AUTO", "0")
os.environ.setdefault("IF_MOCK_REGISTER", "1")

from api.providers import registry
from api.providers.registry import bootstrap
from api.meta import engine


@pytest.fixture(autouse=True)
def _bootstrap(monkeypatch):
    bootstrap()
    # 隔离测试：确保 imagefree provider 的 engine 处于「未注入」的独立状态，
    # 不因前序(集成)测试把全局 registry 单例的 engine 注入而污染 needsengine 分支。
    _img = registry.providers.get("imagefree")
    if _img is not None:
        # 预检 + raising=False：registry 单例可能因 collection 期前序文件（如 test_chat_stream_frames、
        # test_ui_ux_improvements 在 import 期触发 registry 模块分叉/旧实例）而不含 engine 属性。
        # getattr 预检识别分叉旧实例（无 engine 属性），monkeypatch raising=False 兜底，保证不抛
        # AttributeError（P0-1 12 个 ERROR 根因）；无论有无该属性都强制置 None，满足「隔离测试
        # 确保 engine 未注入」意图——有属性则清 None，无属性（旧实例）则补上 None 供
        # test_imagefree_provider_needsengine 走「引擎未注入」分支。
        monkeypatch.setattr(_img, "engine", None, raising=False)
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
        # 号池停用（IF_ACCOUNT_AUTO=0，conftest 默认）时 nanobanana 等需账号提供商被隐藏，
        # 不进 summary；imagefree/aifreeforever 无需账号始终可见。
        assert "imagefree" in s and "aifreeforever" in s
        assert s["aifreeforever"]["needs_proxy_per_request"] is True
        assert s["imagefree"]["needs_account"] is False
        # 号池启用时 nanobanana 才出现；此时断言其 needs_account=True
        if "nanobanana" in s:
            assert s["nanobanana"]["needs_account"] is True
        # P1-E: 验证新增字段
        for prefix in s:
            assert "error_count" in s[prefix], f"{prefix} 缺少 error_count"
            assert "degraded" in s[prefix], f"{prefix} 缺少 degraded"
            assert isinstance(s[prefix]["error_count"], int), f"{prefix} error_count 不是 int"
            assert isinstance(s[prefix]["degraded"], bool), f"{prefix} degraded 不是 bool"
            # 初始状态无连续失败，error_count 应为 0
            assert s[prefix]["error_count"] == 0, f"{prefix} error_count 期望 0 实际 {s[prefix]['error_count']}"
            # 初始 health_status 为 healthy，所以 degraded 应为 False
            assert s[prefix]["degraded"] is False, f"{prefix} degraded 期望 False"


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
        tid = await _dispatch_generate(
            type(
                "R",
                (),
                {
                    "prompt": "x",
                    "aspect_ratio": "1:1",
                    "download": False,
                    "model": "imagefree/default",
                    "resolution": "1K",
                    "duration": None,
                    "priority": None,
                },
            )()
        )
        assert tid and (await tmp_db.get(tid)) is not None

        # nanobanana mock 号池 → 后台任务 completed
        prov = registry.providers["nanobanana"]
        monkeypatch.setattr(prov, "_load_accounts", lambda: list(MOCK_ACC))
        monkeypatch.setattr(registry.adaptive_router, "select_best", lambda *a, **kw: "nanobanana")
        await prov.startup()
        tid2 = await _dispatch_generate(
            type(
                "R",
                (),
                {
                    "prompt": "cat",
                    "aspect_ratio": "1:1",
                    "download": False,
                    "model": "nanobanana/nano-banana-pro",
                    "resolution": "1K",
                    "duration": None,
                    "priority": None,
                },
            )()
        )
        for _ in range(50):
            s = (await tmp_db.get(tid2))["status"]
            if s in ("completed", "error"):
                break
            await asyncio.sleep(0.1)
        await prov.shutdown()
        s = (await tmp_db.get(tid2))["status"]
        assert s == "completed", f"expect completed got {s}"
    finally:
        await engine.stop()


@pytest.mark.slow
@pytest.mark.asyncio
async def test_dispatch_generate_non_imagefree_priority(tmp_db, monkeypatch):
    """P1-D: 非 imagefree 路径按 priority 控制并发。
    P0 立即执行（不信号量），P1 有限并发（4），P2 串行排队（1）。
    """
    from api.dispatch import _dispatch_generate, _provider_sem, _HIGH_CONCURRENCY, _NORMAL_CONCURRENCY

    monkeypatch.setattr("api.dispatch.db", tmp_db)
    engine.db = tmp_db
    await engine.start()
    try:
        prov = registry.providers["nanobanana"]
        monkeypatch.setattr(prov, "_load_accounts", lambda: list(MOCK_ACC))
        monkeypatch.setattr(registry.adaptive_router, "select_best", lambda *a, **kw: "nanobanana")
        await prov.startup()

        # 验证信号量按 limit 隔离
        p2_sem = _provider_sem("nanobanana", _NORMAL_CONCURRENCY)
        p1_sem = _provider_sem("nanobanana", _HIGH_CONCURRENCY)
        assert p2_sem is not p1_sem, "P1 与 P2 的信号量实例应不同"

        # 验证 P2 串行：acquire → 再 acquire 会阻塞
        await p2_sem.acquire()
        locked = p2_sem.locked()
        p2_sem.release()
        assert locked, "P2 信号量（limit=1）acquire 后应 locked"

        # 验证 P1 并发 4 个
        for i in range(4):
            await p1_sem.acquire()
        assert p1_sem.locked(), "P1 信号量（limit=4）全部 acquire 后应 locked"
        for i in range(4):
            p1_sem.release()

        # 提交 3 个不同优先级的非 imagefree 任务，验证它们都能完成
        tids = {}
        for prio, label in [(0, "p0"), (1, "p1"), (2, "p2")]:
            tid = await _dispatch_generate(
                type(
                    "R",
                    (),
                    {
                        "prompt": f"priority-{label}",
                        "aspect_ratio": "1:1",
                        "download": False,
                        "model": "nanobanana/nano-banana-pro",
                        "resolution": "1K",
                        "duration": None,
                        "priority": prio,
                    },
                )()
            )
            tids[prio] = tid

        # 等待所有任务完成
        for prio, tid in tids.items():
            for _ in range(50):
                s = (await tmp_db.get(tid))["status"]
                if s in ("completed", "error"):
                    break
                await asyncio.sleep(0.1)
            s = (await tmp_db.get(tid))["status"]
            assert s == "completed", f"priority={prio} task {tid} 期望 completed 实际 {s}"

        await prov.shutdown()
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
        monkeypatch.setattr(registry.adaptive_router, "select_best", lambda *a, **kw: "nanobanana")
        await prov.startup()
        tid = await _dispatch_edit("nanobanana/nano-banana-pro", "make red", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, False)
        for _ in range(50):
            s = (await tmp_db.get(tid))["status"]
            if s in ("completed", "error"):
                break
            await asyncio.sleep(0.1)
        await prov.shutdown()
        s = (await tmp_db.get(tid))["status"]
        err = (await tmp_db.get(tid))["error"]
        assert s == "completed", f"expect completed got {s} err={err}"
    finally:
        await engine.stop()


def test_normalize_model_legacy():
    from api.dispatch import _normalize_model

    assert _normalize_model("default") == "imagefree/default"
    assert _normalize_model("anime") == "imagefree/anime"
    assert _normalize_model("nanobanana/nano-banana-pro") == "nanobanana/nano-banana-pro"
