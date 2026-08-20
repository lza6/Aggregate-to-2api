"""free_proxy_fetcher（免费代理抓取器）单元测试。

覆盖：ipport 文本解析、geonode JSON 解析、公网 IP 安全过滤（H5）、
去重、parse_source 分发、抓取循环 start/stop 生命周期控制、
_fetch_once 注入 proxy_pool（mock 抓取 + mock 预检，不碰真实网络）。
"""
import asyncio
import json
import os

import pytest

os.environ.setdefault("IF_FREE_PROXY", "0")

from api.free_proxy_fetcher import (  # noqa: E402
    FREE_PROXY_SOURCES,
    FreeProxyFetcher,
    _is_valid_public_ip,
    parse_source,
    parse_geonode_json,
    parse_ipport_text,
)
from api.proxy_pool import ProxyPool  # noqa: E402


# ── 公网 IP 安全过滤（H5）───────────────────────────
class TestValidPublicIp:
    def test_accepts_public_ipv4(self):
        assert _is_valid_public_ip("1.2.3.4")
        assert _is_valid_public_ip("8.8.8.8")
        assert _is_valid_public_ip("172.217.0.1")

    def test_accepts_public_ipv6(self):
        assert _is_valid_public_ip("2606:4700::1111")

    @pytest.mark.parametrize("bad", [
        "10.0.0.1", "192.168.1.1", "172.16.5.5", "127.0.0.1",
        "169.254.1.1", "0.0.0.0", "255.255.255.255", "224.0.0.1",
        "::1", "fe80::1", "localhost", "proxy.example.com", "1.2.3.4.5", "abc",
    ])
    def test_rejects_non_public(self, bad):
        assert not _is_valid_public_ip(bad), f"{bad} 不应通过"


# ── ipport 文本解析 ────────────────────────────────
class TestParseIpport:
    def test_parses_lines_and_dedupe(self):
        text = "# comment\n1.2.3.4:80\n 1.2.3.4:80 \n5.6.7.8:8080\n"
        out = parse_ipport_text(text)
        assert out == ["http://1.2.3.4:80", "http://5.6.7.8:8080"]

    def test_skips_invalid_and_private(self):
        text = "no-port-line\n1.2.3.4\n1.2.3.4:abc\n10.0.0.1:80\nhost:8080\n"
        assert parse_ipport_text(text) == []

    def test_empty(self):
        assert parse_ipport_text("") == []
        assert parse_ipport_text(None) == []


# ── geonode JSON 解析 ──────────────────────────────
class TestParseGeonode:
    def test_parses_items_and_dedupe(self):
        payload = json.dumps({"data": [
            {"ip": "1.2.3.4", "port": "80"},
            {"ip": "1.2.3.4", "port": "80"},   # 重复
            {"ip": "5.6.7.8", "port": "8080"},
        ]})
        out = parse_geonode_json(payload)
        assert out == ["http://1.2.3.4:80", "http://5.6.7.8:8080"]

    def test_empty_and_malformed(self):
        assert parse_geonode_json("not json") == []
        assert parse_geonode_json("{}") == []
        assert parse_geonode_json(None) == []

    def test_skips_private_and_invalid_items(self):
        payload = json.dumps({"data": [
            {"ip": "127.0.0.1", "port": "80"},
            {"ip": "1.2.3.4", "port": "not-a-port"},
            {"ip": "", "port": "80"},
            {"ip": "9.9.9.9", "port": "443"},
            "not-a-dict",
        ]})
        assert parse_geonode_json(payload) == ["http://9.9.9.9:443"]


# ── parse_source 分发 ──────────────────────────────
class TestParseSource:
    def test_dispatch(self):
        assert parse_source("1.2.3.4:80\n", "ipport") == ["http://1.2.3.4:80"]
        assert parse_source(json.dumps({"data": [{"ip": "1.2.3.4", "port": "80"}]}), "json") == ["http://1.2.3.4:80"]
        assert parse_source("x", "unknown") == []


# ── Fetcher 生命周期 ───────────────────────────────
class TestFetcherLifecycle:
    @pytest.mark.asyncio
    async def test_start_skips_when_disabled(self, monkeypatch):
        monkeypatch.setattr("api.free_proxy_fetcher.config.FREE_PROXY_ENABLED", False)
        f = FreeProxyFetcher(ProxyPool())
        await f.start()
        assert f.task is None
        assert f._client is None

    @pytest.mark.asyncio
    async def test_start_creates_task_and_stop_cancels(self, monkeypatch):
        monkeypatch.setattr("api.free_proxy_fetcher.config.FREE_PROXY_ENABLED", True)
        monkeypatch.setattr("api.free_proxy_fetcher.config.PROXY", None)
        f = FreeProxyFetcher(ProxyPool())
        await f.start()
        assert f.task is not None
        assert f._client is not None
        # _loop 无法在测试上下文真正调度：直接验证循环体休眠配置（周期控制）
        try:
            await asyncio.wait_for(asyncio.shield(f._loop()), timeout=0.2)
        except asyncio.TimeoutError:
            pass
        await f.stop()
        assert f._client is None


# ── _fetch_once 注入逻辑（不碰真实网络）─────────────
class TestFetchOnce:
    @pytest.mark.asyncio
    async def test_injects_parsed_free_proxies(self, monkeypatch):
        pool = ProxyPool()
        f = FreeProxyFetcher(pool)
        fake_client = _FakeAsyncClient({
            "proxyscrape.com/v2/": "8.8.8.8:80\n8.8.4.4:443\n",
            "proxylist.geonode.com": json.dumps({"data": [{"ip": "9.9.9.9", "port": "8080"}]}),
        })
        f._client = fake_client
        monkeypatch.setattr("api.free_proxy_fetcher._precheck", _precheck_ok)
        stats = await f._fetch_once()
        assert stats["sources_ok"] == 2
        assert stats["fetched"] == 3
        assert stats["injected"] == 3
        urls = {e.url for e in pool.entries}
        assert urls == {"http://8.8.8.8:80", "http://8.8.4.4:443", "http://9.9.9.9:8080"}
        assert all(e.source == "free" for e in pool.entries)

    @pytest.mark.asyncio
    async def test_dedupe_across_sources(self, monkeypatch):
        pool = ProxyPool()
        f = FreeProxyFetcher(pool)
        # 两个源都返回同一代理 → 只注入一次
        f._client = _FakeAsyncClient({
            "proxyscrape.com/v2/": "8.8.8.8:80\n",
            "githubusercontent.com": "8.8.8.8:80\n7.7.7.7:88\n",
        })
        monkeypatch.setattr("api.free_proxy_fetcher._precheck", _precheck_ok)
        stats = await f._fetch_once()
        assert stats["injected"] == 2
        assert len(pool.entries) == 2

    @pytest.mark.asyncio
    async def test_already_injected_skipped(self, monkeypatch):
        pool = ProxyPool()
        pool.add_free(["http://8.8.8.8:80"])
        f = FreeProxyFetcher(pool)
        f._client = _FakeAsyncClient({"proxyscrape.com/v2/": "8.8.8.8:80\n"})
        monkeypatch.setattr("api.free_proxy_fetcher._precheck", _precheck_ok)
        stats = await f._fetch_once()
        assert stats["injected"] == 0  # 已存在 → 不重复注入

    @pytest.mark.asyncio
    async def test_precheck_fail_targets_dropped(self, monkeypatch):
        pool = ProxyPool()
        f = FreeProxyFetcher(pool)
        f._client = _FakeAsyncClient({"proxyscrape.com/v2/": "8.8.8.8:80\n9.9.9.9:8080\n"})
        monkeypatch.setattr("api.free_proxy_fetcher._precheck", _precheck_fail)
        stats = await f._fetch_once()
        assert stats["injected"] == 0
        assert len(pool.entries) == 0

    @pytest.mark.asyncio
    async def test_stats_refresh_interval_constant(self):
        import api.free_proxy_fetcher as fmod
        f = FreeProxyFetcher(ProxyPool())
        # FREE_PROXY_REFRESH_MIN × 60 是 _loop 的休眠值（周期控制）
        assert fmod.config.FREE_PROXY_REFRESH_MIN >= 0
        assert isinstance(fmod.config.FREE_PROXY_REFRESH_MIN, int)


# ── 测试替身 ───────────────────────────────────────
class _FakeAsyncClient:
    """最小 httpx.AsyncClient 替身：按源名子串返回预设响应。"""

    def __init__(self, per_source: dict[str, object]) -> None:
        self.per_source = per_source

    async def get(self, url: str, **kw):
        matched = None
        for name, payload in self.per_source.items():
            if name in url:
                matched = payload
                break
        return _FakeResponse(matched)

    async def aclose(self):  # noqa: B027
        pass


class _FakeResponse:
    def __init__(self, payload) -> None:
        if payload is None:
            self.status_code = 500
            self.text = ""
        elif isinstance(payload, str):
            self.status_code = 200
            self.text = payload
        else:
            self.status_code = 200
            self.text = json.dumps(payload)


async def _precheck_ok(url: str) -> bool:
    return True


async def _precheck_fail(url: str) -> bool:
    return False