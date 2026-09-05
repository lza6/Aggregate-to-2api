"""proxy_tracer（Cloudflare trace 出口探测器）单测。

覆盖：
- _parse_trace 解析 key=value
- _trace_to_geo real_exit 判定（exit_ip != host → True）
- ProxyTracer 一轮探测：monkeypatch httpx.AsyncClient 返回 200/403/超时
- 缓存 TTL（未过期跳过，过期重探）
- apply_trace_result 回填 + 假代理 consecutive_fails
- IF_PROXY_TRACE_ENABLED=False 时不启动
不碰真实网络。
"""
from __future__ import annotations

import asyncio
import os
import time

import httpx
import pytest

os.environ.setdefault("IF_FREE_PROXY", "0")
os.environ.setdefault("IF_PROXY_TRACE_ENABLED", "0")


def _live_mod():
    import sys as _sys
    return _sys.modules["api.proxy_tracer"]


def _live_config():
    import sys as _sys
    return _sys.modules["api.config"]


from api.proxy_pool import ProxyEntry, ProxyPool  # noqa: E402
from api.proxy_tracer import (  # noqa: E402
    ProxyTracer,
    _extract_host,
    _parse_trace,
    _trace_to_geo,
)


# ── _parse_trace ───────────────────────────────────
class TestParseTrace:
    def test_parses_key_value(self):
        text = "fl=4f\r\nip=1.2.3.4\ncolo=SJC\nloc=US\nhttp=HTTP/2\ntls=TLSv1.3\nts=123\n"
        t = _parse_trace(text)
        assert t["ip"] == "1.2.3.4"
        assert t["colo"] == "SJC"
        assert t["loc"] == "US"
        assert t["http"] == "HTTP/2"
        assert t["tls"] == "TLSv1.3"
        assert t["ts"] == "123"

    def test_skips_invalid_and_empty(self):
        assert _parse_trace("") == {}
        assert _parse_trace(None) == {}
        assert _parse_trace("no-equals\n# comment\n\n") == {}

    def test_strips_whitespace(self):
        t = _parse_trace("  ip = 1.2.3.4  \n colo=SJC ")
        assert t["ip"] == "1.2.3.4"
        assert t["colo"] == "SJC"


# ── _extract_host ─────────────────────────────────
class TestExtractHost:
    def test_plain_ip_port(self):
        assert _extract_host("http://1.2.3.4:80") == "1.2.3.4"

    def test_with_credentials(self):
        assert _extract_host("http://user:pass@5.6.7.8:8080") == "5.6.7.8"


# ── _trace_to_geo ─────────────────────────────────
class TestTraceToGeo:
    def test_real_exit_true_when_ip_differs_from_host(self):
        t = {"ip": "9.9.9.9", "colo": "SJC", "loc": "US", "http": "HTTP/2", "tls": "TLSv1.3", "ts": "123"}
        g = _trace_to_geo("1.2.3.4", t)
        assert g["exit_ip"] == "9.9.9.9"
        assert g["real_exit"] is True
        assert g["colo"] == "SJC"
        assert g["code"] == "US"
        assert g["name"] == "美国"
        assert g["emoji"] == "🇺🇸"
        assert "Cloudflare SJC" in g["desc"]
        assert g["ts"] == 123.0

    def test_real_exit_false_when_ip_equals_host(self):
        t = {"ip": "1.2.3.4", "colo": "SJC", "loc": "US"}
        g = _trace_to_geo("1.2.3.4", t)
        assert g["exit_ip"] == "1.2.3.4"
        assert g["real_exit"] is False

    def test_real_exit_false_when_ip_empty(self):
        g = _trace_to_geo("1.2.3.4", {"ip": "", "colo": ""})
        assert g["exit_ip"] == ""
        assert g["real_exit"] is False
        assert g["colo"] == ""

    def test_unknown_loc_falls_back(self):
        t = {"ip": "9.9.9.9", "colo": "XXX", "loc": "ZZ"}
        g = _trace_to_geo("1.2.3.4", t)
        assert g["code"] == "ZZ"
        assert g["name"] == "未知"


# ── ProxyTracer 生命周期 ─────────────────────────
class TestTracerLifecycle:
    @pytest.mark.asyncio
    async def test_start_skips_when_disabled(self, monkeypatch):
        cfg = _live_config()
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_ENABLED", False)
        t = ProxyTracer(ProxyPool())
        await t.start()
        assert t.task is None
        assert t._client is None

    @pytest.mark.asyncio
    async def test_start_creates_task_and_stop_cancels(self, monkeypatch):
        cfg = _live_config()
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_ENABLED", True)
        monkeypatch.setattr(cfg, "FREE_PROXY_REFRESH_MIN", 30)
        # 空池 → _probe_once 直接返回，循环会立即 sleep，stop 能干净取消
        t = ProxyTracer(ProxyPool())
        await t.start()
        assert t.task is not None
        assert t._client is not None
        try:
            await asyncio.wait_for(asyncio.shield(t._loop()), timeout=0.3)
        except TimeoutError:
            pass
        await t.stop()
        assert t.task is None
        assert t._client is None


# ── _pick_targets / 缓存 TTL ─────────────────────
class TestPickTargets:
    def test_picks_only_free_proxies(self, monkeypatch):
        cfg = _live_config()
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_TTL", 3600)
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_MAX_PER_ROUND", 50)
        pool = ProxyPool()
        pool.entries = [
            ProxyEntry("http://1.1.1.1:80", source="residential"),
            ProxyEntry("http://2.2.2.2:80", source="free"),
            ProxyEntry("http://3.3.3.3:80", source="free"),
        ]
        t = ProxyTracer(pool)
        targets = t._pick_targets()
        assert "http://2.2.2.2:80" in targets
        assert "http://3.3.3.3:80" in targets
        assert "http://1.1.1.1:80" not in targets

    def test_skips_cached_within_ttl(self, monkeypatch):
        cfg = _live_config()
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_TTL", 3600)
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_MAX_PER_ROUND", 50)
        pool = ProxyPool()
        pool.entries = [
            ProxyEntry("http://2.2.2.2:80", source="free"),
        ]
        t = ProxyTracer(pool)
        # 已缓存且未过期 → 跳过
        t._cache["http://2.2.2.2:80"] = {"ts": time.time(), "exit_ip": "9.9.9.9"}
        assert t._pick_targets() == []

    def test_reprobes_after_ttl_expiry(self, monkeypatch):
        cfg = _live_config()
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_TTL", 1)
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_MAX_PER_ROUND", 50)
        pool = ProxyPool()
        pool.entries = [ProxyEntry("http://2.2.2.2:80", source="free")]
        t = ProxyTracer(pool)
        # 缓存时间早于 TTL → 过期 → 需重探
        t._cache["http://2.2.2.2:80"] = {"ts": time.time() - 100, "exit_ip": "9.9.9.9"}
        assert t._pick_targets() == ["http://2.2.2.2:80"]

    def test_max_per_round_caps_targets(self, monkeypatch):
        cfg = _live_config()
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_TTL", 3600)
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_MAX_PER_ROUND", 2)
        pool = ProxyPool()
        pool.entries = [
            ProxyEntry(f"http://{i}.{i}.{i}.{i}:80", source="free") for i in range(1, 6)
        ]
        t = ProxyTracer(pool)
        assert len(t._pick_targets()) == 2

    def test_prefers_recently_active(self, monkeypatch):
        cfg = _live_config()
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_TTL", 3600)
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_MAX_PER_ROUND", 1)
        pool = ProxyPool()
        pool.entries = [
            ProxyEntry("http://1.1.1.1:80", source="free"),
            ProxyEntry("http://2.2.2.2:80", source="free"),
        ]
        pool.entries[0].last_used_at = time.time() - 10
        pool.entries[1].last_used_at = time.time()  # 更近活跃
        t = ProxyTracer(pool)
        assert t._pick_targets() == ["http://2.2.2.2:80"]


# ── _probe_once + apply_trace_result 回填 ─────────
class _FakeSuccessClient:
    """每次 get 返回 200 + 合法 trace（exit_ip=9.9.9.9）。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        class _R:
            status_code = 200
            text = ("fl=4f\nip=9.9.9.9\ncolo=SJC\nloc=US\n"
                    "http=HTTP/2\ntls=TLSv1.3\nts=" + str(int(time.time())))
        return _R()


class _Fake403Client:
    """每次 get 返回 403（所有端点都失败 → _fetch_trace 返回 None）。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        class _R:
            status_code = 403
            text = ""
        return _R()


class _FakeTimeoutClient:
    """每次 get 超时（所有端点失败 → _fetch_trace 返回 None）。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        raise httpx.TimeoutException("simulated timeout")


class _FakeIpEqualsHostClient:
    """trace ip == 代理 host（real_exit=False → 假代理）。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        class _R:
            status_code = 200
            text = "ip=2.2.2.2\ncolo=SJC\nloc=US\nts=" + str(int(time.time()))
        return _R()


class TestFetchTrace:
    @pytest.mark.asyncio
    async def test_fetch_trace_success(self, monkeypatch):
        mod = _live_mod()
        cfg = _live_config()
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_ENABLED", True)
        t = ProxyTracer(ProxyPool())
        t._client = None  # _fetch_trace 自建 client
        monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **kw: _FakeSuccessClient())
        result = await t._fetch_trace("http://1.2.3.4:80")
        assert result is not None
        assert result["ip"] == "9.9.9.9"

    @pytest.mark.asyncio
    async def test_fetch_trace_returns_none_on_403(self, monkeypatch):
        mod = _live_mod()
        monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **kw: _Fake403Client())
        t = ProxyTracer(ProxyPool())
        assert await t._fetch_trace("http://1.2.3.4:80") is None

    @pytest.mark.asyncio
    async def test_fetch_trace_returns_none_on_timeout(self, monkeypatch):
        mod = _live_mod()
        monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **kw: _FakeTimeoutClient())
        t = ProxyTracer(ProxyPool())
        assert await t._fetch_trace("http://1.2.3.4:80") is None


class TestProbeOnce:
    @pytest.mark.asyncio
    async def test_probe_once_real_exit_backfills_pool_and_cache(self, monkeypatch):
        mod = _live_mod()
        cfg = _live_config()
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_TTL", 3600)
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_MAX_PER_ROUND", 50)
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_CONCURRENCY", 8)
        monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **kw: _FakeSuccessClient())
        pool = ProxyPool()
        pool.entries = [ProxyEntry("http://2.2.2.2:80", source="free")]
        t = ProxyTracer(pool)
        stats = await t._probe_once()
        assert stats["probed"] == 1
        assert stats["ok"] == 1
        assert stats["real_exit"] == 1
        assert stats["failed"] == 0
        e = pool.entries[0]
        assert e.exit_ip == "9.9.9.9"
        assert e.real_exit is True
        assert e.trace_ts > 0
        assert e.consecutive_fails == 0  # real_exit → 清零
        assert "http://2.2.2.2:80" in t._cache
        # 出口 IP 预热进 geo cache
        from api.geo_ip import _GEO_CACHE
        assert "9.9.9.9" in _GEO_CACHE

    @pytest.mark.asyncio
    async def test_probe_once_fake_proxy_increments_fails(self, monkeypatch):
        mod = _live_mod()
        cfg = _live_config()
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_TTL", 3600)
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_MAX_PER_ROUND", 50)
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_CONCURRENCY", 8)
        monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **kw: _FakeIpEqualsHostClient())
        pool = ProxyPool()
        pool.entries = [ProxyEntry("http://2.2.2.2:80", source="free")]
        pool.entries[0].consecutive_fails = 2
        t = ProxyTracer(pool)
        stats = await t._probe_once()
        assert stats["probed"] == 1
        assert stats["ok"] == 1
        assert stats["real_exit"] == 0  # 假代理
        e = pool.entries[0]
        assert e.exit_ip == "2.2.2.2"
        assert e.real_exit is False
        assert e.consecutive_fails == 3  # 增量

    @pytest.mark.asyncio
    async def test_probe_once_all_failed(self, monkeypatch):
        mod = _live_mod()
        cfg = _live_config()
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_TTL", 3600)
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_MAX_PER_ROUND", 50)
        monkeypatch.setattr(cfg, "IF_PROXY_TRACE_CONCURRENCY", 8)
        monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **kw: _Fake403Client())
        pool = ProxyPool()
        pool.entries = [ProxyEntry("http://2.2.2.2:80", source="free")]
        t = ProxyTracer(pool)
        stats = await t._probe_once()
        assert stats["probed"] == 1
        assert stats["ok"] == 0
        assert stats["failed"] == 1
        assert pool.entries[0].exit_ip == ""  # 未回填

    @pytest.mark.asyncio
    async def test_probe_once_empty_pool_returns_zero(self, monkeypatch):
        t = ProxyTracer(ProxyPool())
        stats = await t._probe_once()
        assert stats["probed"] == 0
        assert stats["ok"] == 0
        assert stats["failed"] == 0
