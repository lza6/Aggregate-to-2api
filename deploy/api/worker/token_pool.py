"""_TokenPool 单 key token 池 + TokenPoolManager 多 key 管理。

由原单体 api/worker.py 拆分而来，逻辑与注释保持原样。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from urllib.parse import urlsplit

from .. import config
from .. import turnstile_client
from ..solver_guard import solver_guard

log = logging.getLogger("engine")


def _safe_proxy_label(key: str) -> str:
    """观测面脱敏：代理 URL 含 user:pass 凭据，healthz/metrics 只暴露 host:port。"""
    if key == "direct":
        return "direct"
    try:
        u = urlsplit(key)
        host = u.hostname or key
        return f"{host}:{u.port}" if u.port else host
    except (ValueError, TypeError):
        return hashlib.sha256(key.encode("utf-8", "replace")).hexdigest()[:12]


class _TokenPool:
    """单个 key 的 token 池。

    key="direct" 为直连池（动态水位：无排队时维持 1 个新鲜 token，有排队补满 TOKEN_POOL_SIZE）；
    key=代理 URL 为 per-proxy 池（固定水位 EDIT_PROXY_POOL_SIZE，token 与出口代理 IP 绑定）。
    预取由 need_event 事件驱动（acquire 池空时置位立即唤醒）+ 1.0s 轮询兜底。
    """

    def __init__(self, key: str, target_getter, maxsize: int, idle_ttl: float,
                 proxy: str | None, engine=None):
        # key: "direct" 或代理 URL；target_getter: () -> int 动态目标水位
        self.key = key
        self.safe_key = _safe_proxy_label(key)
        self.target_getter = target_getter
        self.maxsize = maxsize
        self.idle_ttl = idle_ttl
        # q 存 (token, produced_ts)，取用前按 TOKEN_TTL 检查是否过期（H1）
        self.q: asyncio.Queue[tuple[str, float]] = asyncio.Queue(maxsize=maxsize)
        # need_event: 池空时 acquire set → 预取立即补，事件驱动替代轮询
        self.need_event = asyncio.Event()
        # last_activity: acquire/put 刷新；proxy 池空闲回收用
        self.last_activity = time.time()
        self.task: asyncio.Task | None = None
        # 全局求解并发信号量（manager 注入，等价 manager.sem）
        self.sem: asyncio.Semaphore | None = None
        # proxy: key != "direct" 时传 turnstile_client 的 proxy 参数
        self.proxy = proxy
        # IMP-02: 求解耗时 EMA（指数移动平均），初始 5.0s
        self._ema: float = 5.0
        # P-04: Engine 引用，用于动态水位计算
        self._engine = engine

    async def acquire(self, timeout: float) -> str | None:
        """取未过期 token；池空则置位 need_event 等预取补池；超时返回 None。"""
        deadline = time.monotonic() + timeout
        while True:
            self._prune_expired()
            if not self.q.empty():
                token, ts = self.q.get_nowait()
                if time.time() - ts <= config.TOKEN_TTL:
                    self.last_activity = time.time()
                    self._signal_if_empty()
                    return token
                log.info("取到过期 token，丢弃重取[%s]", self.key)
                continue
            self.last_activity = time.time()
            self.need_event.set()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                token, ts = await asyncio.wait_for(self.q.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return None
            if time.time() - ts <= config.TOKEN_TTL:
                self.last_activity = time.time()
                self._signal_if_empty()
                return token
            log.info("预取补入的 token 已过期，丢弃重取[%s]", self.key)

    def _signal_if_empty(self) -> None:
        """取走 token 后若池空，置位 need_event 通知预取立即补池。"""
        if self.q.empty():
            self.need_event.set()

    def update_solve_time(self, duration: float) -> None:
        """IMP-02: 更新求解耗时 EMA（指数移动平均），供自适应延迟使用。"""
        alpha = config.IF_PREFETCH_EMA_ALPHA
        self._ema = self._ema * (1 - alpha) + duration * alpha

    def _target_watermark(self) -> int:
        """P-04: 基于入队深度的动态水位。

        有排队时提升至 maxsize 上限，空闲回落保底 1 个新鲜 token。
        """
        if self._engine is None:
            return 1
        solve_time = self._ema
        qsize = 0
        try:
            qsize = self._engine.queue.qsize()
        except Exception:
            pass
        if qsize > 0:
            return self.maxsize
        expected = 1.0
        return min(int(expected), self.maxsize)

    def _get_prefetch_delay(self) -> float:
        """IMP-02: 计算预取延迟。固定值或 EMA 自适应。"""
        if config.IF_PREFETCH_AFTER_SOLVE_DELAY > 0:
            return config.IF_PREFETCH_AFTER_SOLVE_DELAY
        return max(0.5, min(self._ema * 0.5, 3.0))

    async def prefetch_loop(self) -> None:
        """持续补满本池；池满等 need_event（acquire 触发）事件驱动唤醒。"""
        while True:
            try:
                self._prune_expired()
                open_circuit = solver_guard.circuit_open
                if open_circuit:
                    if not solver_guard.allow_solve():
                        await asyncio.sleep(1.0)
                        continue
                    need = max(self._target_watermark() - self.q.qsize(), 1)
                else:
                    need = self._target_watermark() - self.q.qsize()
                    if need <= 0:
                        if self.need_event.is_set():
                            self.need_event.clear()
                            continue
                        await self.need_event.wait()
                        self.need_event.clear()
                        continue
                try:
                    async with self.sem:
                        token, solve_time = await turnstile_client.solve_turnstile(
                            config.CF_SOLVER_URL, config.BASE_URL, config.SITEKEY,
                            config.TURNSTILE_TIMEOUT, proxy=self.proxy)
                    if token and not self.q.full():
                        await self.q.put((token, time.time()))
                        self.need_event.clear()
                        self.update_solve_time(solve_time)
                        delay = self._get_prefetch_delay()
                        await asyncio.sleep(delay)
                except Exception as e:
                    log.warning("token 预取失败[%s]: %s", self.key, e)
                    await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("token 预取循环异常[%s]: %s", self.key, e)
                await asyncio.sleep(2.0)

    def _prune_expired(self) -> None:
        """丢弃池中已过 TOKEN_TTL 的 token（无 await，事件循环内原子，安全）。"""
        now = time.time()
        kept: list[tuple[str, float]] = []
        while not self.q.empty():
            token, ts = self.q.get_nowait()
            if now - ts <= config.TOKEN_TTL:
                kept.append((token, ts))
            else:
                log.info("丢弃过期 token（已存活 %.0fs）[%s]", now - ts, self.key)
        for item in kept:
            try:
                self.q.put_nowait(item)
            except asyncio.QueueFull:
                break

    def size(self) -> int:
        return self.q.qsize()

    def snapshot(self) -> dict:
        """{"key","size","target","idle"} key 为脱敏标识。"""
        return {
            "key": self.safe_key,
            "size": self.q.qsize(),
            "target": self._target_watermark(),
            "idle": time.time() - self.last_activity > self.idle_ttl,
        }


class TokenPoolManager:
    """多 key token 池管理：per-key 独立池、事件驱动补池、懒创建、空闲回收、熔断门控、动态水位。"""

    def __init__(self, engine):
        self.engine = engine
        self.pools: dict[str, _TokenPool] = {}
        self.sem = asyncio.Semaphore(max(1, config.TOKEN_PREFETCH_CONCURRENCY))
        self.wait_timeout_total = 0
        self._reaper: asyncio.Task | None = None

    async def start(self) -> None:
        """创建并启动 direct 池 + 启动空闲回收守护协程。"""
        self._ensure_pool("direct")
        self._reaper = asyncio.create_task(self._reap_idle_proxy_pools())

    async def stop(self) -> None:
        """取消所有 prefetch 协程 + reaper，等真正退出避免孤儿任务告警。"""
        if self._reaper:
            self._reaper.cancel()
        pools = list(self.pools.values())
        for pool in pools:
            if pool.task:
                pool.task.cancel()
        tasks = [t for t in [self._reaper, *[p.task for p in pools]] if t and not t.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def acquire(self, key: str, timeout: float) -> str | None:
        """取指定 key 池的 token；池不存在则懒创建。超时返回 None 时累计 wait_timeout_total。"""
        pool = self._ensure_pool(key)
        if solver_guard.circuit_open and pool.q.empty():
            return None
        token = await pool.acquire(timeout)
        if token is None:
            self.wait_timeout_total += 1
        return token

    def _ensure_pool(self, key: str) -> _TokenPool:
        """懒创建池。direct: 动态水位；proxy: 固定水位、空闲回收 TTL。"""
        pool = self.pools.get(key)
        if pool is not None:
            if self.engine._started and pool.task is None:
                pool.task = asyncio.create_task(pool.prefetch_loop())
            return pool
        if key == "direct":
            pool = _TokenPool(
                key,
                lambda: config.TOKEN_POOL_SIZE,
                config.TOKEN_POOL_SIZE,
                idle_ttl=float("inf"),
                proxy=None,
                engine=self.engine,
            )
        else:
            pool = _TokenPool(
                key,
                lambda: config.EDIT_PROXY_POOL_SIZE,
                max(config.TOKEN_POOL_SIZE, config.EDIT_PROXY_POOL_SIZE),
                idle_ttl=config.EDIT_PROXY_POOL_IDLE_TTL,
                proxy=key,
                engine=self.engine,
            )
        pool.sem = self.sem
        self.pools[key] = pool
        if not self.engine._started:
            return pool
        pool.task = asyncio.create_task(pool.prefetch_loop())
        return pool

    async def _reap_idle_proxy_pools(self) -> None:
        """守护循环：每 60s 检查，per-proxy 池空闲超 TTL → 回收。"""
        while True:
            await asyncio.sleep(60)
            now = time.time()
            reaped: list[asyncio.Task | None] = []
            for key in list(self.pools):
                if key == "direct":
                    continue
                pool = self.pools[key]
                if now - pool.last_activity > pool.idle_ttl:
                    if pool.task:
                        pool.task.cancel()
                    del self.pools[key]
                    reaped.append(pool.task)
                    log.info("回收空闲代理池 %s（空闲 %.0fs 超 TTL）", key, now - pool.last_activity)
            if reaped:
                await asyncio.gather(*[t for t in reaped if t], return_exceptions=True)

    def pools_snapshot(self) -> dict:
        """{"direct": {...}, "proxy:<host:port>": {...}} 取各池 snapshot。"""
        out: dict = {}
        for key, pool in self.pools.items():
            label = "direct" if key == "direct" else f"proxy:{pool.safe_key}"
            out[label] = pool.snapshot()
        return out

    def direct_queue(self) -> asyncio.Queue:
        """返回 direct 池的 q（兼容 engine.token_pool 转发）。"""
        return self._ensure_pool("direct").q

    def direct_pool_size(self) -> int:
        return self._ensure_pool("direct").q.qsize()