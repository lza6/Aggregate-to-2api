"""ISSUE-03: Action Sniffer 单元测试（HTML/JS 解析提取、双级缓存、失配自愈重试）。

用 MockTransport 模拟上游 HTML/JS，不依赖真实网络。
"""
from __future__ import annotations

import os

import httpx

os.environ.setdefault("IF_ACCOUNT_AUTO", "0")
os.environ.setdefault("IF_MOCK_REGISTER", "1")

from api.providers import action_sniffer as asn
from api.providers.action_sniffer import (
    ActionSniffer,
    STATIC_ACTION_IDS,
    extract_js_urls,
    extract_server_actions,
    is_stale_action_response,
)

# ── 上游 Mock 素材（与 nanobanana-pro.com 2026-08 实测格式一致）──────────────
CHUNK_CLAIM = (
    'var a = r(34477);'
    'let n = (0,a.createServerReference)("7fb1e44a9ba4fc6d7acb30a875856c8f9ff7c595a0",a.callServer,void 0,a.findSourceMapURL,"claimDailyCheckinAction"),'
    'i=(0,a.createServerReference)("7f6220d6529913353e7fefbb3918e37baf2b5c7a77",a.callServer,void 0,a.findSourceMapURL,"getCreditStatsAction");'
)
CHUNK_GEN = (
    'g=(0,i.createServerReference)("7f904a2139cb876e6ab21eba10c5d73793b5f060a6",i.callServer,void 0,i.findSourceMapURL,"unifiedGenerateImageAction");'
    'var h=(0,i.createServerReference)("7fb13306a33c45210271155f5a19aa5bf2f1fa118f",i.callServer,void 0,i.findSourceMapURL,"unifiedEditImageAction");'
)
MOCK_HTML = (
    "<html><head>"
    '<script src="/_next/static/chunks/3257-80d4da8a99bc77b1.js"></script>'
    '<script src="/_next/static/chunks/6121-ae9fef44a868c7cf.js"></script>'
    '<link rel="preload" as="script" href="/_next/static/chunks/main-app-3669b313013e9073.js">'
    "</head><body><div id=\"root\"></div></body></html>"
)


def _mock_transport(*, fail: bool = False) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if fail:
            raise httpx.ConnectError("模拟断网", request=request)
        url = str(request.url)
        if url.endswith("/zh") or url.rstrip("/") == "https://nanobanana-pro.com":
            return httpx.Response(200, text=MOCK_HTML)
        if "3257-" in url:
            return httpx.Response(200, text=CHUNK_CLAIM)
        if "6121-" in url:
            return httpx.Response(200, text=CHUNK_GEN)
        return httpx.Response(404, text="not found")
    return httpx.MockTransport(handler)


def _sniffer(tmp_path, **kw) -> ActionSniffer:
    return ActionSniffer(
        "https://nanobanana-pro.com",
        persist_path=str(tmp_path / "action_ids.json"),
        **kw,
    )


# ── 1. HTML/JS 解析提取 ─────────────────────────────
def test_extract_server_actions_maps_names_to_ids():
    found = extract_server_actions(CHUNK_CLAIM + CHUNK_GEN)
    assert found["claimDailyCheckinAction"] == "7fb1e44a9ba4fc6d7acb30a875856c8f9ff7c595a0"
    assert found["unifiedGenerateImageAction"] == "7f904a2139cb876e6ab21eba10c5d73793b5f060a6"
    assert found["unifiedEditImageAction"] == "7fb13306a33c45210271155f5a19aa5bf2f1fa118f"


def test_extract_js_urls_dedups_and_resolves():
    urls = extract_js_urls(MOCK_HTML, "https://nanobanana-pro.com")
    assert "https://nanobanana-pro.com/_next/static/chunks/3257-80d4da8a99bc77b1.js" in urls
    assert "https://nanobanana-pro.com/_next/static/chunks/6121-ae9fef44a868c7cf.js" in urls
    assert len(urls) == len(set(urls))


def test_nearby_action_id_fallback():
    text = 'const map = {"7fb1e44a9ba4fc6d7acb30a875856c8f9ff7c595a0": ref, "claimDailyCheckinAction": fn};'
    assert asn._nearby_action_id(text, "claimDailyCheckinAction") == "7fb1e44a9ba4fc6d7acb30a875856c8f9ff7c595a0"


def test_is_stale_action_response():
    assert is_stale_action_response(httpx.Response(404, text="not found")) is True
    assert is_stale_action_response(httpx.Response(200, text='{"error":"action not found"}')) is True
    assert is_stale_action_response(httpx.Response(200, text='0:{"success":true,"taskId":"T1"}')) is False
    assert is_stale_action_response(httpx.Response(500, text="upstream boom")) is False


# ── 2. 嗅探 / 双级缓存 ─────────────────────────────
async def test_sniff_parses_all_actions(tmp_path):
    s = _sniffer(tmp_path, transport=_mock_transport())
    try:
        found = await s.refresh()
        assert found["generate"] == "7f904a2139cb876e6ab21eba10c5d73793b5f060a6"
        assert found["edit"] == "7fb13306a33c45210271155f5a19aa5bf2f1fa118f"
        assert found["claim_daily_checkin"] == "7fb1e44a9ba4fc6d7acb30a875856c8f9ff7c595a0"
        # 内存缓存命中
        assert await s.get_action_id("generate") == "7f904a2139cb876e6ab21eba10c5d73793b5f060a6"
    finally:
        await s.aclose()


async def test_get_action_id_cache_hit_no_network(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        url = str(request.url)
        if url.endswith("/zh"):
            return httpx.Response(200, text=MOCK_HTML)
        if "3257-" in url:
            return httpx.Response(200, text=CHUNK_CLAIM)
        if "6121-" in url:
            return httpx.Response(200, text=CHUNK_GEN)
        return httpx.Response(404)

    s = _sniffer(tmp_path, transport=httpx.MockTransport(handler))
    try:
        first = await s.get_action_id("generate")
        assert first == "7f904a2139cb876e6ab21eba10c5d73793b5f060a6"
        n_after_first = calls["n"]
        second = await s.get_action_id("generate")
        assert second == first
        assert calls["n"] == n_after_first, "缓存命中不应再发网络请求"
    finally:
        await s.aclose()


async def test_force_refresh_re_sniffs(tmp_path):
    counter = {"n": 0}

    def handler(request):
        counter["n"] += 1
        url = str(request.url)
        if url.endswith("/zh"):
            return httpx.Response(200, text=MOCK_HTML)
        return httpx.Response(200, text=CHUNK_CLAIM if "3257-" in url else CHUNK_GEN)

    s = _sniffer(tmp_path, transport=httpx.MockTransport(handler))
    try:
        await s.get_action_id("generate")
        base = counter["n"]
        await s.get_action_id("generate", force_refresh=True)
        assert counter["n"] > base, "force_refresh 必须触发新的网络嗅探"
    finally:
        await s.aclose()


def test_cache_persist_roundtrip(tmp_path):
    path = str(tmp_path / "action_ids.json")
    s1 = ActionSniffer("https://nanobanana-pro.com", persist_path=path)
    s1.seed("generate", "7fdeadbeef00000000000000000000000000000000")
    s2 = ActionSniffer("https://nanobanana-pro.com", persist_path=path)
    assert s2.peek("generate") == "7fdeadbeef00000000000000000000000000000000"
    # 未持久化的 kind 回退静态兜底
    assert s2.peek("claim_daily_checkin") == STATIC_ACTION_IDS["claim_daily_checkin"]


async def test_fallback_to_static_on_network_failure(tmp_path):
    s = _sniffer(tmp_path, transport=_mock_transport(fail=True))
    try:
        assert await s.get_action_id("generate") == STATIC_ACTION_IDS["generate"]
        assert await s.get_action_id("claim_daily_checkin") == STATIC_ACTION_IDS["claim_daily_checkin"]
    finally:
        await s.aclose()


async def test_keepalive_refresh_when_stale(tmp_path):
    import asyncio

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        url = str(request.url)
        if url.endswith("/zh"):
            return httpx.Response(200, text=MOCK_HTML)
        return httpx.Response(200, text=CHUNK_CLAIM if "3257-" in url else CHUNK_GEN)

    s = _sniffer(tmp_path, transport=httpx.MockTransport(handler))
    s._last_sniff_at = 0.0  # 模拟从未嗅探过
    s.start_keepalive(interval_seconds=1)
    try:
        for _ in range(40):
            if s.peek("generate") != STATIC_ACTION_IDS["generate"]:
                break
            await asyncio.sleep(0.1)
    finally:
        s.stop_keepalive()
        await s.aclose()
    assert s.peek("generate") == "7f904a2139cb876e6ab21eba10c5d73793b5f060a6"
    assert calls["n"] >= 1


# ── 3. Provider 失配自愈重试 ─────────────────────────
class FakeSniffer:
    """可控 Fake Sniffer：首次返回旧 ID，force_refresh 后返回新 ID。"""

    def __init__(self, stale: str, fresh: str) -> None:
        self.current = stale
        self.fresh = fresh
        self.force_calls = 0

    async def get_action_id(self, kind: str, *, force_refresh: bool = False) -> str:
        if force_refresh:
            self.force_calls += 1
            self.current = self.fresh
        return self.current

    def start_keepalive(self, *a, **k) -> None:
        pass

    def stop_keepalive(self) -> None:
        pass

    async def aclose(self) -> None:
        pass


class FakeClient:
    """按序返回预设响应的假 httpx 客户端，记录每次 POST 的 Next-Action。"""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def post(self, url, headers=None, content=None, **kw):
        self.calls.append({"url": url, "action_id": headers.get("Next-Action")})
        return self.responses.pop(0)


def _make_provider(stale: str, fresh: str, responses: list[httpx.Response]):
    from api.providers.nanobanana import NanobananaProvider

    p = NanobananaProvider()
    p._action_sniffer = FakeSniffer(stale, fresh)
    p._client = FakeClient(responses)
    return p


async def test_provider_self_heal_on_404():
    """首 POST 404（失配）→ force_refresh 嗅探到新 ID → 用新 ID 自愈重试成功。"""
    p = _make_provider(
        stale="7fold",
        fresh="7fnew0123456789abcdef0123456789abcdef0123",
        responses=[
            httpx.Response(404, text="not found"),
            httpx.Response(200, text='0:{"success":true,"taskId":"T1"}'),
        ],
    )
    task_id = await p._submit_image("cookie", "nano-banana-pro", "cat", "1:1", "1K")
    assert task_id == "T1"
    assert p._action_sniffer.force_calls == 1
    assert p._client.calls[0]["action_id"] == "7fold"
    assert p._client.calls[1]["action_id"] == "7fnew0123456789abcdef0123456789abcdef0123"


async def test_provider_no_retry_on_success():
    """首 POST 即成功 → 不触发嗅探、不重试。"""
    p = _make_provider(
        stale="7fok",
        fresh="7fnew0123456789abcdef0123456789abcdef0123",
        responses=[httpx.Response(200, text='0:{"success":true,"taskId":"T9"}')],
    )
    task_id = await p._submit_image("cookie", "nano-banana-pro", "cat", "1:1", "1K")
    assert task_id == "T9"
    assert p._action_sniffer.force_calls == 0
    assert len(p._client.calls) == 1


async def test_provider_edit_self_heal():
    """图生图 edit action 同样自愈（上传成功后，action 失配触发新 ID 重试）。"""
    p = _make_provider(
        stale="7feold",
        fresh="7fenew0123456789abcdef0123456789abcdef0123",
        responses=[
            httpx.Response(404, text="not found"),
            httpx.Response(200, text='0:{"success":true,"taskId":"E2"}'),
        ],
    )
    p._client.responses.insert(0, httpx.Response(200, json={"url": "https://assets.example/x.png"}))

    task_id = await p._submit_edit("cookie", "nano-banana-pro", "make red",
                                   "1:1", [b"\x89PNG\r\n" + b"\x00" * 32])
    assert task_id == "E2"
    assert p._action_sniffer.force_calls == 1
    # 调用顺序：0=upload, 1=失配(旧ID), 2=自愈重试(新ID)
    assert len(p._client.calls) == 3
    assert p._client.calls[1]["action_id"] == "7feold"
    assert p._client.calls[2]["action_id"] == "7fenew0123456789abcdef0123456789abcdef0123"


# ── 4. registerer 签到响应解析 ───────────────────────
def test_registerer_claim_response_ok():
    from api.registerer import NanobananaRegisterer

    ok = httpx.Response(200, text='0:{"success":true,"data":{"rewardAmount":4}}')
    assert NanobananaRegisterer._claim_response_ok(ok) is True
    ok2 = httpx.Response(200, text='0:{"data":{"rewardAmount":8}}')
    assert NanobananaRegisterer._claim_response_ok(ok2) is True
    bad = httpx.Response(200, text='0:{"error":"failed"}')
    assert NanobananaRegisterer._claim_response_ok(bad) is False
    not_action = httpx.Response(200, text="<html>not-an-action</html>")
    assert NanobananaRegisterer._claim_response_ok(not_action) is False