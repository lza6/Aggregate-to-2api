"""Playwright 浏览器即服务池（fal.ai minimax-H3 专用）。

设计动机：fal.ai 的 minimax-H3 链路在每步 fetch 上要求 Kasada `x-is-human`
注入与 hCaptcha token 绑定出口 IP；把这些抠出来用 httpx 重放会被 Kasada
拦截。改为在 Playwright page 上下文里 `page.evaluate(fetch(...))` 执行整条
链路，让 Kasada 自动注入 `x-is-human`，cookie/csrf 与 IP 在同一 page 内闭环。

每个借出的 page 绑定一个出口代理（从 proxy_pool 取），整条链路共用同一
IP/cookie/csrf。池大小由 `IF_FALAI_BROWSER_POOL_SIZE` 控制（默认 2）。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from . import config

log = logging.getLogger("browser_pool")


class BrowserPool:
    """管理 N 个 Playwright chromium 实例，每个绑定一个出口代理。

    懒加载：首次 acquire 才启动 playwright + 浏览器。`acquire` 借出 page，
    `release` 归还（page 复用，不关闭）。整池 stop 时关闭所有浏览器与
    playwright 实例。
    """

    def __init__(self, pool_size: int | None = None, headful: bool | None = None,
                 proxy_pool: Any | None = None) -> None:
        self.pool_size = int(pool_size if pool_size is not None
                             else config.IF_FALAI_BROWSER_POOL_SIZE)
        self.headful = bool(headful if headful is not None
                            else config.IF_FALAI_BROWSER_HEADFUL)
        self._proxy_pool = proxy_pool
        self._slots: list[dict[str, Any]] = []  # 每个 slot: {browser, context, page, proxy}
        self._sem = asyncio.Semaphore(max(1, self.pool_size))
        self._started = False
        self._stopping = False
        self._playwright = None
        # slot 维护：归还时复用，不在 acquire 中重建 page（保留 cookie/出口）
        self._next_slot = 0

    def _resolve_proxy(self) -> str | None:
        """从 proxy_pool 取一个出口代理（同步包装；acquire 路径已异步）。"""
        if self._proxy_pool is None:
            return None
        try:
            return self._proxy_pool.acquire  # type: ignore[return-value]
        except AttributeError:
            return None

    async def _proxy_acquire(self) -> str | None:
        """异步取一个出口代理（lifespan 注入的 proxy_pool.acquire 是协程）。"""
        if self._proxy_pool is None:
            return None
        try:
            return await self._proxy_pool.acquire()
        except Exception as e:  # noqa: BLE001
            log.warning("browser_pool 取代理失败: %s", e)
            return None

    async def _ensure_started(self) -> None:
        if self._started:
            return
        if self.pool_size <= 0:
            raise RuntimeError("IF_FALAI_BROWSER_POOL_SIZE<=0，浏览器池未启用")
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError(
                "playwright 未安装；请运行: pip install playwright && playwright install chromium"
            ) from e
        self._playwright = await async_playwright().start()
        launch_args = ["--disable-blink-features=AutomationControlled"]
        for i in range(self.pool_size):
            proxy_url = await self._proxy_acquire()
            launch_kwargs: dict[str, Any] = {
                "args": launch_args,
                "headless": not self.headful,
            }
            if proxy_url:
                launch_kwargs["proxy"] = {"server": proxy_url}
            try:
                browser = await self._playwright.chromium.launch(**launch_kwargs)
            except Exception as e:  # noqa: BLE001
                log.warning("browser_pool 启动 chromium 失败 slot=%d: %s", i, e)
                continue
            context = await browser.new_context()
            page = await context.new_page()
            self._slots.append({
                "browser": browser,
                "context": context,
                "page": page,
                "proxy": proxy_url,
            })
        if not self._slots:
            raise RuntimeError("browser_pool 启动后无可用 slot（chromium 启动全部失败）")
        self._started = True
        log.info("browser_pool 启动完成 %d/%d slot", len(self._slots), self.pool_size)

    async def acquire(self) -> tuple[Any, Any]:
        """借出 (browser, page)。池空时阻塞等待。"""
        if self._stopping:
            raise RuntimeError("browser_pool 正在停止，无法 acquire")
        await self._sem.acquire()
        await self._ensure_started()
        slot = self._slots[self._next_slot % len(self._slots)]
        self._next_slot += 1
        return slot["browser"], slot["page"]

    def release(self) -> None:
        """归还一个 slot（不关闭 page，复用 cookie/csrf/出口）。"""
        self._sem.release()

    async def start(self) -> None:
        """显式启动（lifespan 调用；失败记日志不抛，保持 lazy 兜底）。"""
        if self._started:
            return
        try:
            await self._ensure_started()
        except Exception as e:  # noqa: BLE001
            log.warning("browser_pool 显式启动失败（lazy 兜底）: %s", e)

    async def stop(self) -> None:
        """关闭所有浏览器与 playwright 实例（幂等）。"""
        if self._stopping:
            return
        self._stopping = True
        for slot in self._slots:
            try:
                await slot["context"].close()
            except Exception:  # noqa: BLE001
                pass
            try:
                await slot["browser"].close()
            except Exception:  # noqa: BLE001
                pass
        self._slots.clear()
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
            self._playwright = None
        self._started = False
        self._stopping = False

    @property
    def started(self) -> bool:
        return self._started

    def snapshot(self) -> dict:
        return {
            "pool_size": self.pool_size,
            "slots": len(self._slots),
            "started": self._started,
            "headful": self.headful,
        }


# 模块单例（lifespan 绑定 proxy_pool 后注入到 falai provider）
browser_pool = BrowserPool()


__all__ = ["BrowserPool", "browser_pool"]
