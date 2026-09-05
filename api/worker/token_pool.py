"""_TokenPool 单 key token 池 + TokenPoolManager 多 key 管理。

升级支持 Turnstile Token 预热与双缓冲池 (Double-Buffering & Zero-Latency Fetch)：
- 每个 Pool 维护 Active Buffer (主消费队列) 和 Standby Buffer (备用预热队列)。
- 请求优先从 Active Buffer 0ms 获取未过期 token；
- 当 Active Buffer 消耗至低水位或为空时，无缝原子切换 (Swap) 至 Standby Buffer，
  并触发后台协程自适应补齐新的 Standby Buffer，实现全天候 0 毫秒零排队取用。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any, Callable
from urllib.parse import urlsplit

from .. import config, turnstile_client
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
    """单个 key 的双缓冲 token 池 (Double-Buffering Token Pool)。

    - active_q: 当前对外提供消费的主队列；
    - standby_q: 后台持续预热的备用队列；
    - 兼容属性 self.q 指向 active_q。
    """

    def __init__(
        self,
        key: str,
        target_getter: Callable[[], int],
        maxsize: int,
        idle_ttl: float,
        proxy: str | None,
        engine: Any = None,
    ) -> None:
        self.key = key
        self.safe_key = _safe_proxy_label(key)
        self.target_getter = target_getter
        self.maxsize = maxsize
        self.idle_ttl = idle_ttl

        # 双缓冲区：Active 与 Standby
        buffer_cap = max(2, maxsize // 2) if maxsize > 2 else maxsize
        self.buffer_cap = buffer_cap
        self.active_q: asyncio.Queue[tuple[str, float]] = asyncio.Queue(maxsize=self.buffer_cap)
        self.standby_q: asyncio.Queue[tuple[str, float]] = asyncio.Queue(maxsize=self.buffer_cap)

        # 统计计数
        self.buffer_swaps_total = 0
        self.zero_latency_hits = 0
        self.acquire_total = 0

        self.need_event = asyncio.Event()
        self.last_activity = time.time()
        self.task: asyncio.Task[None] | None = None
        self.sem: asyncio.Semaphore | None = None
        self.proxy = proxy
        self._ema: float = 5.0
        self._engine = engine

    @property
    def q(self) -> asyncio.Queue[tuple[str, float]]:
        """向后兼容属性：返回当前 active_q。"""
        return self.active_q

    def _swap_buffers(self) -> bool:
        """如果 standby 队列有 token，原子切换至 active 队列。"""
        self._prune_queue(self.standby_q)
        if not self.standby_q.empty():
            # 交换引用
            self.active_q, self.standby_q = self.standby_q, self.active_q
            self.buffer_swaps_total += 1
            self.need_event.set()
            log.debug("Token pool [%s] 双缓冲切换: active_size=%d", self.key, self.active_q.qsize())
            return True
        return False

    async def acquire(self, timeout: float) -> str | None:
        """取未过期 token；优先从 Active 取，若空则尝试 Swap Standby；全部为空时置位 need_event 等待。"""
        self.acquire_total += 1
        deadline = time.monotonic() + timeout

        while True:
            self._prune_expired()

            # 1. 尝试从 Active Buffer 快速获取 (0ms Hit)
            if not self.active_q.empty():
                token, ts = self.active_q.get_nowait()
                if time.time() - ts <= config.TOKEN_TTL:
                    self.zero_latency_hits += 1
                    self.last_activity = time.time()
                    self._check_low_watermark()
                    return token
                log.info("Active Buffer 取到过期 token，丢弃重取[%s]", self.key)
                continue

            # 2. Active 为空，尝试立即从 Standby Buffer Swap
            if self._swap_buffers():
                continue

            # 3. 双缓冲均空，置位事件驱动补充并等待
            self.last_activity = time.time()
            self.need_event.set()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None

            try:
                # 监听 active_q 或 standby_q 的补充
                token, ts = await asyncio.wait_for(self.active_q.get(), timeout=remaining)
            except asyncio.TimeoutError:
                # 再次尝试从 standby 看看是否刚补充完成
                if self._swap_buffers():
                    continue
                return None

            if time.time() - ts <= config.TOKEN_TTL:
                self.last_activity = time.time()
                self._check_low_watermark()
                return token
            log.info("预取补入的 token 已过期，丢弃重取[%s]", self.key)

    def _check_low_watermark(self) -> None:
        """当 Active 或 Standby 水位偏低时触发补充。"""
        if self.active_q.qsize() <= 1 or self.standby_q.empty():
            self.need_event.set()

    def update_solve_time(self, duration: float) -> None:
        """更新求解耗时 EMA（指数移动平均）。"""
        alpha = config.IF_PREFETCH_EMA_ALPHA
        self._ema = self._ema * (1 - alpha) + duration * alpha

    def _target_watermark(self) -> int:
        """基于排队深度和动态水位配置（P0-3 双水位）。

        direct 池：
        - 有排队（qsize>0）→ 返回 maxsize（满负荷补池）；
        - 无排队 → 返回 TOKEN_TARGET_WATERMARK（默认1=旧逻辑，生产建议5保持预热）。
        per-proxy 池：沿用 target_getter（EDIT_PROXY_POOL_SIZE）。
        """
        if self.key != "direct":
            return int(self.target_getter())
        if self._engine is None:
            return max(1, config.TOKEN_TARGET_WATERMARK)
        qsize = 0
        try:
            qsize = self._engine.queue.qsize()
        except Exception:
            pass
        if qsize > 0:
            return self.maxsize
        return max(1, config.TOKEN_TARGET_WATERMARK)

    def _is_urgent(self) -> bool:
        """P0-3 紧急水位：total 低于 TOKEN_URGENT_WATERMARK 时触发批量并发填充。

        默认 0 = 关闭批量（走旧单次填充，向后兼容）；>0 时 total<urgent 即紧急。
        生产建议 urgent=2：池将空时一次并发填 N 个，避免逐个填充期间请求干等。
        """
        if config.TOKEN_URGENT_WATERMARK <= 0:
            return False
        total = self.active_q.qsize() + self.standby_q.qsize()
        return total < config.TOKEN_URGENT_WATERMARK

    def _get_prefetch_delay(self) -> float:
        """计算预取延迟：固定配置优先，否则自适应（EMA 指数衰减）。"""
        if config.IF_PREFETCH_AFTER_SOLVE_DELAY > 0:
            return config.IF_PREFETCH_AFTER_SOLVE_DELAY
        # v4.2 回归：测试与旧版注释均约定“EMA 的一半”语义。
        # 原实现 *0.3 与配置文档 IF_PREFETCH_EMA_HALF 命名冲突，恢复为 *0.5。
        return max(0.5, min(self._ema * 0.5, 3.0))

    async def _solve_one(self) -> tuple[str, float] | None:
        """单次求解（经 semaphore 限流 + 走 turnstile_client 集群调度）。返回 (token, solve_time) 或 None。"""
        try:
            async with self.sem:  # type: ignore[union-attr]
                token, solve_time = await turnstile_client.solve_turnstile(
                    cf_solver_url=None,
                    url=config.BASE_URL,
                    sitekey=config.SITEKEY,
                    timeout=config.TURNSTILE_TIMEOUT,
                    proxy=self.proxy,
                )
            return token, solve_time
        except Exception as e:
            log.warning("token 预取失败[%s]: %s", self.key, e)
            return None

    async def _batch_fill(self, n: int) -> int:
        """P0-3 批量并发填充：一次并发 n 个 solve，把成功结果塞入非满队列。

        返回成功填入的 token 数。n 钳到 >=1；n=1 等价单次填充（向后兼容）。
        真并发受 self.sem（TOKEN_PREFETCH_CONCURRENCY）与 cf_solver 多槽（P0-1）共同约束。
        """
        n = max(1, n)
        results = await asyncio.gather(*(self._solve_one() for _ in range(n)), return_exceptions=True)
        filled = 0
        for r in results:
            if isinstance(r, Exception) or r is None:
                continue
            token, solve_time = r
            if not token:
                continue
            self.update_solve_time(solve_time)
            # 优先塞 active，满则塞 standby，都满则弃（池已满）
            target_queue = self.active_q if not self.active_q.full() else self.standby_q
            if target_queue.full():
                continue
            try:
                await target_queue.put((token, time.time()))
                filled += 1
            except asyncio.QueueFull:
                continue
        return filled

    async def prefetch_loop(self) -> None:
        """双缓冲预热循环：依次填满 Active 与 Standby 队列。

        P0-3：当 _is_urgent()（total < TOKEN_URGENT_WATERMARK）且 TOKEN_BATCH_FILL_SIZE>1 时，
        走批量并发填充（asyncio.gather）一次补 N 个，避免逐个填充期间请求干等。
        默认 urgent=0/batch=1 = 关闭批量，完全保持旧单次填充行为（向后兼容）。
        """
        while True:
            try:
                self._prune_expired()
                open_circuit = solver_guard.circuit_open
                if open_circuit:
                    if not solver_guard.allow_solve():
                        await asyncio.sleep(1.0)
                        continue

                # 计算总持有量与目标
                total_current = self.active_q.qsize() + self.standby_q.qsize()
                target = self._target_watermark()

                if total_current >= target and self.active_q.full() and self.standby_q.full():
                    if self.need_event.is_set():
                        self.need_event.clear()
                        continue
                    await self.need_event.wait()
                    self.need_event.clear()
                    continue

                # P0-3 批量并发填充分支：urgent 且 batch>1
                if self._is_urgent() and config.TOKEN_BATCH_FILL_SIZE > 1:
                    batch_n = config.TOKEN_BATCH_FILL_SIZE
                    filled = await self._batch_fill(batch_n)
                    if filled > 0:
                        # 批量填充后按 EMA 延迟节流（防 cf_solver 429）
                        delay = self._get_prefetch_delay()
                        await asyncio.sleep(delay)
                    else:
                        await asyncio.sleep(2.0)  # 全失败 → 退避
                    continue

                # 优先补充 Active 队列，其次补充 Standby
                target_queue = self.active_q if not self.active_q.full() else self.standby_q

                res = await self._solve_one()
                if res is not None:
                    token, solve_time = res
                    if token and not target_queue.full():
                        await target_queue.put((token, time.time()))
                        self.update_solve_time(solve_time)
                        delay = self._get_prefetch_delay()
                        await asyncio.sleep(delay)
                else:
                    await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("token 预取循环异常[%s]: %s", self.key, e)
                await asyncio.sleep(2.0)

    def _prune_queue(self, q: asyncio.Queue[tuple[str, float]]) -> None:
        """清理队列中过期的 token。"""
        now = time.time()
        kept: list[tuple[str, float]] = []
        while not q.empty():
            token, ts = q.get_nowait()
            if now - ts <= config.TOKEN_TTL:
                kept.append((token, ts))
            else:
                log.debug("丢弃过期 token（已存活 %.0fs）[%s]", now - ts, self.key)
        for item in kept:
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                break

    def _prune_expired(self) -> None:
        """清理双缓冲中的过期 token。"""
        self._prune_queue(self.active_q)
        self._prune_queue(self.standby_q)

    def size(self) -> int:
        return self.active_q.qsize() + self.standby_q.qsize()

    def snapshot(self) -> dict[str, Any]:
        """包含双缓冲明细与零延迟命中率快照。"""
        act_size = self.active_q.qsize()
        std_size = self.standby_q.qsize()
        hit_rate = round(self.zero_latency_hits / self.acquire_total, 4) if self.acquire_total > 0 else 1.0
        return {
            "key": self.safe_key,
            "size": act_size + std_size,
            "active_size": act_size,
            "standby_size": std_size,
            "target": self._target_watermark(),
            "buffer_swaps_total": self.buffer_swaps_total,
            "zero_latency_hits": self.zero_latency_hits,
            "zero_latency_hit_rate": hit_rate,
            "idle": time.time() - self.last_activity > self.idle_ttl,
        }


class TokenPoolManager:
    """多 key token 池管理：per-key 独立双缓冲池、事件驱动补池、懒创建、空闲回收。"""

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.pools: dict[str, _TokenPool] = {}
        self.sem = asyncio.Semaphore(max(1, config.TOKEN_PREFETCH_CONCURRENCY))
        self.wait_timeout_total = 0
        self._reaper: asyncio.Task[None] | None = None

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
        """取指定 key 池的 token；池不存在则懒创建。"""
        pool = self._ensure_pool(key)
        if solver_guard.circuit_open and pool.size() == 0:
            return None
        token = await pool.acquire(timeout)
        if token is None:
            self.wait_timeout_total += 1
        return token

    def _ensure_pool(self, key: str) -> _TokenPool:
        """懒创建双缓冲池。"""
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
            reaped: list[asyncio.Task[None] | None] = []
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

    def pools_snapshot(self) -> dict[str, Any]:
        """取各池双缓冲快照。"""
        out: dict[str, Any] = {}
        for key, pool in self.pools.items():
            label = "direct" if key == "direct" else f"proxy:{pool.safe_key}"
            out[label] = pool.snapshot()
        return out

    def direct_queue(self) -> asyncio.Queue[tuple[str, float]]:
        """返回 direct 池当前 active_q。"""
        return self._ensure_pool("direct").active_q

    def direct_pool_size(self) -> int:
        return self._ensure_pool("direct").size()
