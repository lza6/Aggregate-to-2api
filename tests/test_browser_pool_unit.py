"""api/browser_pool.py BrowserPool 单元测试（P0-2 覆盖率补强，mock playwright）。

覆盖：pool_size/headful 解析、_resolve_proxy/_proxy_acquire、_ensure_started 启动链
（playwright 未装/import 失败/launch 失败）、acquire/release 信号量、start/stop 幂等、
snapshot。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.browser_pool import BrowserPool

# ── 构造与属性 ───────────────────────────────────────────────


def test_constructor_defaults(monkeypatch):
    monkeypatch.setattr("api.browser_pool.config.IF_FALAI_BROWSER_POOL_SIZE", 3)
    monkeypatch.setattr("api.browser_pool.config.IF_FALAI_BROWSER_HEADFUL", False)
    pool = BrowserPool()
    assert pool.pool_size == 3
    assert pool.headful is False
    assert pool.started is False
    snap = pool.snapshot()
    assert snap == {"pool_size": 3, "slots": 0, "started": False, "headful": False}


def test_constructor_explicit():
    pool = BrowserPool(pool_size=2, headful=True, proxy_pool=None)
    assert pool.pool_size == 2
    assert pool.headful is True
    assert pool._proxy_pool is None


# ── _resolve_proxy / _proxy_acquire ─────────────────────────


def test_resolve_proxy_no_pool_returns_none():
    assert BrowserPool(proxy_pool=None)._resolve_proxy() is None


def test_resolve_proxy_attr_access():
    proxy_pool = MagicMock()
    proxy_pool.acquire = "proxy://1.2.3.4:8080"  # 属性（非方法）
    pool = BrowserPool(pool_size=1, proxy_pool=proxy_pool)
    assert pool._resolve_proxy() == "proxy://1.2.3.4:8080"


def test_resolve_proxy_attr_missing_returns_none():
    proxy_pool = MagicMock()
    del proxy_pool.acquire  # 没有 acquire 属性
    pool = BrowserPool(pool_size=1, proxy_pool=proxy_pool)
    assert pool._resolve_proxy() is None


@pytest.mark.asyncio
async def test_proxy_acquire_success():
    proxy_pool = MagicMock()
    proxy_pool.acquire = AsyncMock(return_value="proxy://x:1")
    pool = BrowserPool(pool_size=1, proxy_pool=proxy_pool)
    assert await pool._proxy_acquire() == "proxy://x:1"


@pytest.mark.asyncio
async def test_proxy_acquire_exception_returns_none():
    proxy_pool = MagicMock()
    proxy_pool.acquire = AsyncMock(side_effect=RuntimeError("pool empty"))
    pool = BrowserPool(pool_size=1, proxy_pool=proxy_pool)
    assert await pool._proxy_acquire() is None


@pytest.mark.asyncio
async def test_proxy_acquire_no_pool_returns_none():
    pool = BrowserPool(pool_size=1, proxy_pool=None)
    assert await pool._proxy_acquire() is None


# ── _ensure_started：playwright 未装 / launch 失败 ────────────


@pytest.mark.asyncio
async def test_ensure_started_pool_size_zero_raises(monkeypatch):
    pool = BrowserPool(pool_size=0)
    with pytest.raises(RuntimeError, match="IF_FALAI_BROWSER_POOL_SIZE"):
        await pool._ensure_started()


@pytest.mark.asyncio
async def test_ensure_started_playwright_not_installed(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "playwright.async_api":
            raise ImportError("no playwright")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    pool = BrowserPool(pool_size=2, proxy_pool=None)
    with pytest.raises(RuntimeError, match="playwright 未安装"):
        await pool._ensure_started()


def _make_fake_playwright(slots_ok: int = 2, proxy_pool=None):
    """构造 fake playwright.async_api.async_playwright + chromium，按 slots_ok 决定 launch 成功数。"""
    slots: list[dict[str, Any]] = []

    async def _noop(*a, **kw):
        return None

    async def _launch(**kwargs):
        idx = len(slots)
        if idx >= slots_ok:
            raise RuntimeError("launch failed")
        ctx = MagicMock()
        ctx.close = AsyncMock()
        page = MagicMock()
        ctx.new_page = AsyncMock(return_value=page)
        browser = MagicMock()
        browser.close = AsyncMock()
        browser.new_context = AsyncMock(return_value=ctx)
        slots.append({"browser": browser, "context": ctx, "page": page})
        return browser

    chromium = MagicMock()
    chromium.launch = _launch
    pw = MagicMock()
    pw.chromium = chromium
    pw.stop = AsyncMock()

    class _PlaywrightCtx:
        async def start(self):
            return pw

    mod = MagicMock()
    mod.async_playwright = lambda: _PlaywrightCtx()
    return mod, slots


@pytest.mark.asyncio
async def test_ensure_started_success(monkeypatch):
    import sys

    mod, slots = _make_fake_playwright(slots_ok=2)
    monkeypatch.setitem(sys.modules, "playwright.async_api", mod)
    pool = BrowserPool(pool_size=2, proxy_pool=MagicMock(acquire=AsyncMock(return_value=None)))
    await pool._ensure_started()
    assert pool.started is True
    assert len(pool._slots) == 2


@pytest.mark.asyncio
async def test_ensure_started_all_launch_fail_raises(monkeypatch):
    import sys

    mod, _ = _make_fake_playwright(slots_ok=0)
    monkeypatch.setitem(sys.modules, "playwright.async_api", mod)
    pool = BrowserPool(pool_size=2, proxy_pool=MagicMock(acquire=AsyncMock(return_value=None)))
    with pytest.raises(RuntimeError, match="无可用 slot"):
        await pool._ensure_started()


@pytest.mark.asyncio
async def test_ensure_started_idempotent(monkeypatch):
    import sys

    mod, _ = _make_fake_playwright(slots_ok=1)
    monkeypatch.setitem(sys.modules, "playwright.async_api", mod)
    pool = BrowserPool(pool_size=1, proxy_pool=MagicMock(acquire=AsyncMock(return_value=None)))
    await pool._ensure_started()
    slots_before = len(pool._slots)
    await pool._ensure_started()  # 二次调用不重复创建
    assert len(pool._slots) == slots_before


# ── acquire / release ───────────────────────────────────────


@pytest.mark.asyncio
async def test_acquire_release_roundtrip(monkeypatch):
    import sys

    mod, _ = _make_fake_playwright(slots_ok=2)
    monkeypatch.setitem(sys.modules, "playwright.async_api", mod)
    pool = BrowserPool(pool_size=2, proxy_pool=MagicMock(acquire=AsyncMock(return_value=None)))
    browser, page = await pool.acquire()
    assert browser is not None and page is not None
    pool.release()
    # 再次 acquire 应能拿到（信号量已释放，slot 复用机制不保证对象同一性）
    b2, p2 = await pool.acquire()
    assert b2 is not None and p2 is not None
    pool.release()


@pytest.mark.asyncio
async def test_acquire_while_stopping_raises(monkeypatch):
    pool = BrowserPool(pool_size=1)
    pool._stopping = True
    with pytest.raises(RuntimeError, match="正在停止"):
        await pool.acquire()


# ── start / stop ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_failure_logged_not_raised(monkeypatch):
    pool = BrowserPool(pool_size=0)  # _ensure_started 必失败
    await pool.start()  # 不抛（lazy 兜底）
    assert pool.started is False


@pytest.mark.asyncio
async def test_start_idempotent_when_started(monkeypatch):
    import sys

    mod, _ = _make_fake_playwright(slots_ok=1)
    monkeypatch.setitem(sys.modules, "playwright.async_api", mod)
    pool = BrowserPool(pool_size=1, proxy_pool=MagicMock(acquire=AsyncMock(return_value=None)))
    await pool.start()
    assert pool.started
    await pool.start()  # 不抛
    assert pool.started


@pytest.mark.asyncio
async def test_stop_closes_all_and_idempotent(monkeypatch):
    import sys

    mod, slots = _make_fake_playwright(slots_ok=2)
    monkeypatch.setitem(sys.modules, "playwright.async_api", mod)
    pool = BrowserPool(pool_size=2, proxy_pool=MagicMock(acquire=AsyncMock(return_value=None)))
    await pool.start()
    # 记录 mock playwright 供 stop 关闭
    pool._playwright = mod.async_playwright().start.__self__ if False else pool._playwright
    await pool.stop()
    assert pool.started is False
    assert pool._slots == []
    # 二次 stop 幂等不抛
    await pool.stop()
