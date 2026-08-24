"""高并发执行引擎：有界队列 + worker 池 + 多 key Turnstile token 池管理器。

设计目标：入口扛 50 RPS。请求只做 校验 → INSERT(SQLite 毫秒级) → 入队(内存) → 返回，
不在请求路径上同步做任何慢操作。真正的生成由后台 worker 池消费。

Turnstile 求解是最贵的串行资源（cf_solver 单槽 5s/token），所以：
- 后台预取协程（per-key）持续补满 token 池，请求来临时直接拿现成 token（不阻塞在求解）。
- 事件驱动补池：池空时 acquire 置位 need_event 立即唤醒预取，替代原 sleep 轮询的 latency 尖峰。
- 多 key：direct 直连池 + per-proxy 池（图生图代理模式 token 与出口代理 IP 绑定，不可跨池复用）。
- 熔断门控：solver_guard 熔断 OPEN 期间暂停新求解（快速失败，不再 30s 干等）；
- 动态水位：direct 池无排队时维持 1 个新鲜 token（避免满池空转重解），有排队补满；
- 空闲回收：per-proxy 池空闲超 TTL 自动回收（释放 cf_solver 浏览器上下文）。
- 池满即停，不空闲浪费；token 用后即弃（一次性）。
"""
import asyncio
import hashlib
import logging
import time
import uuid
from urllib.parse import urlsplit

from . import config
from . import imagefree_client
from . import turnstile_client
from .db import QueueDB
from .retry_policy import RetryPolicy
# 注意：solver_guard 模块内定义了同名单例实例，须导入实例本身（`from . import solver_guard`
# 会绑到模块对象，`solver_guard.allow_solve()` 将 AttributeError）。
from .solver_guard import solver_guard
from .telemetry import get_tracer
# S-4: 慢日志画像打点 + S-7: worker 心跳
from .slow_log import SlowSample, slow_log
from .worker_health import worker_health

log = logging.getLogger("engine")


def _safe_proxy_label(key: str) -> str:
    """观测面脱敏：代理 URL 含 user:pass 凭据，healthz/metrics 只暴露 host:port。

    key="direct" 原样；解析失败回退 sha256 截断（不泄漏完整 URL）。
    """
    if key == "direct":
        return "direct"
    try:
        u = urlsplit(key)
        host = u.hostname or key
        return f"{host}:{u.port}" if u.port else host
    except (ValueError, TypeError):
        return hashlib.sha256(key.encode("utf-8", "replace")).hexdigest()[:12]


class QueueFull(RuntimeError):
    """队列已满（入口限流）。"""


# 上游判定「turnstile token 无效/被拒绝」的关键信号（重试条件）。
# 这类失败是瞬时性的：换一个新 token 重新提交大概率成功，所以 worker 会自动重试。
_TOKEN_REJECTED_MARKERS = ("human verification failed",)


def _is_token_rejected(err: object) -> bool:
    """判断失败是否由 token 被上游拒绝引起（可换 token 重试）。"""
    msg = str(err).lower()
    return any(m in msg for m in _TOKEN_REJECTED_MARKERS)


class CountedPriorityQueue(asyncio.PriorityQueue):
    """支持优先级计数的 PriorityQueue 子类。

    内部维护 _counts 字典按优先级计数，put/get 时自动更新。
    支持 per-priority 上限判定（is_full / put_nowait 时抛 QueueFull）。
    """

    def __init__(self, maxsize=0, limits=None):
        super().__init__(maxsize=maxsize)
        self._counts: dict[int, int] = {0: 0, 1: 0, 2: 0}
        self._limits: dict[int, int] = limits or {0: 200, 1: 500, 2: 1500}

    def put_nowait(self, item):
        priority = item[0]
        if self._counts.get(priority, 0) >= self._limits.get(priority, 9999):
            raise asyncio.QueueFull
        super().put_nowait(item)
        self._counts[priority] = self._counts.get(priority, 0) + 1

    def get_nowait(self):
        item = super().get_nowait()
        self._counts[item[0]] = max(0, self._counts.get(item[0], 0) - 1)
        return item

    async def get(self):
        item = await super().get()
        self._counts[item[0]] = max(0, self._counts.get(item[0], 0) - 1)
        return item

    def count(self, priority=None):
        if priority is not None:
            return self._counts.get(priority, 0)
        return sum(self._counts.values())

    def is_full(self, priority):
        return self._counts.get(priority, 0) >= self._limits.get(priority, 9999)


class _TokenPool:
    """单个 key 的 token 池。

    key="direct" 为直连池（动态水位：无排队时维持 1 个新鲜 token，有排队补满 TOKEN_POOL_SIZE）；
    key=代理 URL 为 per-proxy 池（固定水位 EDIT_PROXY_POOL_SIZE，token 与出口代理 IP 绑定）。
    预取由 need_event 事件驱动（acquire 池空时置位立即唤醒）+ 1.0s 轮询兜底，替代原 sleep 轮询。
    """

    def __init__(self, key: str, target_getter, maxsize: int, idle_ttl: float,
                 proxy: str | None, engine=None):
        # key: "direct" 或代理 URL；target_getter: () -> int 动态目标水位
        self.key = key
        # 观测面脱敏标识（direct 或 host:port），healthz/metrics 用，不泄漏代理 user:pass
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
        # IMP-02: 求解耗时 EMA（指数移动平均），初始 5.0s（默认单次求解约 5s）
        self._ema: float = 5.0
        # P-04: Engine 引用，用于动态水位计算
        self._engine = engine

    async def acquire(self, timeout: float) -> str | None:
        """取未过期 token；池空则置位 need_event 等预取补池；超时返回 None；取到过期 token 丢弃重取。"""
        deadline = time.monotonic() + timeout
        while True:
            self._prune_expired()
            if not self.q.empty():
                token, ts = self.q.get_nowait()
                if time.time() - ts <= config.TOKEN_TTL:
                    self.last_activity = time.time()
                    self._signal_if_empty()   # 取走最后一个 token → 池空立即唤醒预取（事件驱动）
                    return token
                log.info("取到过期 token，丢弃重取[%s]", self.key)
                continue
            # 池空：刷新 last_activity（「正在尝试使用」也算活动，防 reaper 在 acquire 等待时
            # 回收本池 → 干等 30s 悬挂）；置位 need_event 通知预取协程立即补池；
            # 等新 token 入池（q.get 天然阻塞，不自旋）
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
                self._signal_if_empty()   # 从等待路径拿到最后一个 token 同样要唤醒预取（否则事件丢失 → 补池停摆）
                return token
            log.info("预取补入的 token 已过期，丢弃重取[%s]", self.key)
            # 过期 token 已取出（一次性），继续循环等新鲜的

    def _signal_if_empty(self) -> None:
        """取走 token 后若池空，置位 need_event 通知预取立即补池（防事件丢失停摆）。"""
        if self.q.empty():
            self.need_event.set()

    def update_solve_time(self, duration: float) -> None:
        """IMP-02: 更新求解耗时 EMA（指数移动平均），供自适应延迟使用。"""
        alpha = config.IF_PREFETCH_EMA_ALPHA
        self._ema = self._ema * (1 - alpha) + duration * alpha

    def _target_watermark(self) -> int:
        """P-04: 基于入队深度的动态水位。

        目标 = min((队列深度/窗口) * solve_time * 1.5, maxsize)，空闲时维持 1 个新鲜 token。
        同步路径（token 预取循环内无法 await）：用队列深度近似入队速率。
        有排队时提升至 TOKEN_POOL_SIZE 上限，空闲回落保底 1。
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
            # 有排队：直接补满池上限（预取循环按 need 消费，避免欠补）
            return self.maxsize
        expected = max(1, 0.0 * solve_time * 1.5)
        return min(int(expected), self.maxsize)

    def _get_prefetch_delay(self) -> float:
        """IMP-02: 计算预取延迟。IF_PREFETCH_AFTER_SOLVE_DELAY > 0 时使用固定值，否则使用 EMA 自适应。"""
        if config.IF_PREFETCH_AFTER_SOLVE_DELAY > 0:
            return config.IF_PREFETCH_AFTER_SOLVE_DELAY
        return max(0.5, min(self._ema * 0.5, 3.0))

    async def prefetch_loop(self) -> None:
        """持续补满本池；池满等 need_event（acquire 触发）事件驱动唤醒。

        熔断 OPEN：暂停常规补池，但按 allow_solve() 半开节奏放行探测求解（成功即恢复）。
        池里残留 token 不阻止探测——否则恢复要等残留 token 过期（最坏 TOKEN_TTL 秒）。
        求解并发受全局信号量限制（TOKEN_PREFETCH_CONCURRENCY），cf_solver 是串行贵资源。
        """
        while True:
            try:
                self._prune_expired()
                open_circuit = solver_guard.circuit_open
                if open_circuit:
                    # 半开探测：每 probe_interval 放行一次求解，验证求解器是否恢复
                    if not solver_guard.allow_solve():
                        await asyncio.sleep(1.0)
                        continue
                    # 探测至少求解 1 次（即使池满/有残留 token）
                    need = max(self._target_watermark() - self.q.qsize(), 1)
                else:
                    need = self._target_watermark() - self.q.qsize()
                    if need <= 0:
                        # 事件驱动补池：acquire 池空必置位 need_event（含取空路径，见 acquire）。
                        # wait 前清残留事件防 busy-loop；Event.wait() 无超时（cancel 安全，无
                        # wait_for 在 3.11 的 cancel 竞态）；set 早于 wait() 也立即返回（无丢失窗口）。
                        if self.need_event.is_set():
                            self.need_event.clear()
                            continue
                        await self.need_event.wait()
                        self.need_event.clear()
                        continue
                try:
                    async with self.sem:  # 全局求解并发（TOKEN_PREFETCH_CONCURRENCY）
                        token, solve_time = await turnstile_client.solve_turnstile(
                            config.CF_SOLVER_URL, config.BASE_URL, config.SITEKEY,
                            config.TURNSTILE_TIMEOUT, proxy=self.proxy)
                    if token and not self.q.full():
                        await self.q.put((token, time.time()))
                        # 注意：不刷新 last_activity——后台维持 token 不算「使用」，
                        # 否则代理池永远不算空闲、空闲回收失效。仅 acquire 成功时刷新。
                        self.need_event.clear()
                        # IMP-02: 更新求解耗时 EMA 并计算自适应延迟
                        self.update_solve_time(solve_time)
                        delay = self._get_prefetch_delay()
                        await asyncio.sleep(delay)
                except Exception as e:
                    # 失败已由 turnstile_client 统一上报 solver_guard；backoff 防自旋
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
            except asyncio.QueueFull:  # pragma: no cover - 刚清空过，理论不可达
                break

    def size(self) -> int:
        return self.q.qsize()

    def snapshot(self) -> dict:
        """{"key","size","target","idle"} key 为脱敏标识（direct|host:port，不泄漏代理凭据）。

        idle=自上次成功取 token 起空闲超过 idle_ttl。注意：prefetch 后台补池不刷新
        last_activity（维持 token 不算使用），否则代理池永不判定 idle、空闲回收失效。
        仅 acquire 成功取 token 时刷新。
        """
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
        self.wait_timeout_total = 0          # 池空 acquire 超时累计次数（metrics 用）
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
        """取指定 key 池的 token；池不存在则懒创建。超时返回 None 时累计 wait_timeout_total。

        熔断 OPEN 时：池里现成 token 仍可用（求解失败≠token 无效），池空则快速失败
        （不再 30s 干等）。探测求解由 prefetch_loop 独占 allow_solve() 节奏，acquire 不抢
        探测机会，否则半开恢复会被干等路径挤占。
        """
        pool = self._ensure_pool(key)
        if solver_guard.circuit_open and pool.q.empty():
            return None
        token = await pool.acquire(timeout)
        if token is None:
            self.wait_timeout_total += 1
        return token

    def _ensure_pool(self, key: str) -> _TokenPool:
        """懒创建池。direct: 动态水位（P-04: _target_watermark 基于入队速率和求解耗时）；
        proxy: 固定水位、空闲回收 TTL。"""
        pool = self.pools.get(key)
        if pool is not None:
            # 引擎已启动但该池无 prefetch task（如启动前懒创建残留）→ 补启动，防 token 饥饿
            if self.engine._started and pool.task is None:
                pool.task = asyncio.create_task(pool.prefetch_loop())
            return pool
        if key == "direct":
            pool = _TokenPool(
                key,
                lambda: config.TOKEN_POOL_SIZE,
                config.TOKEN_POOL_SIZE,
                idle_ttl=float("inf"),   # direct 池不空闲回收
                proxy=None,
                engine=self.engine,
            )
        else:
            # per-proxy 池：token 与出口代理 IP 绑定，不可跨池复用；目标水位固定 EDIT_PROXY_POOL_SIZE。
            # maxsize 取两者较大值，防 EDIT_PROXY_POOL_SIZE > TOKEN_POOL_SIZE 时预取「求解→丢」空转。
            pool = _TokenPool(
                key,
                lambda: config.EDIT_PROXY_POOL_SIZE,
                max(config.TOKEN_POOL_SIZE, config.EDIT_PROXY_POOL_SIZE),
                idle_ttl=config.EDIT_PROXY_POOL_IDLE_TTL,
                proxy=key,   # key 即代理 URL，透传给 turnstile_client
                engine=self.engine,
            )
        pool.sem = self.sem
        self.pools[key] = pool
        if not self.engine._started:
            # 引擎未启动（纯构造/测试场景）：只建池不启动后台预取，由 start() 统一负责，
            # 避免孤儿 prefetch 协程在关闭的事件循环里报 "Task was destroyed"。
            return pool
        pool.task = asyncio.create_task(pool.prefetch_loop())
        return pool

    async def _reap_idle_proxy_pools(self) -> None:
        """守护循环：每 60s 检查，per-proxy 池自上次成功取 token 起空闲超 TTL → 回收（停止预取、释放资源）。"""
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
        """{"direct": {...}, "proxy:<host:port>": {...}} 取各池 snapshot（healthz/metrics 用）。

        标签用脱敏标识（safe_key），不泄漏代理 URL 中的 user:pass 凭据。
        """
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


class _WorkerHandle:
    """Worker 句柄：唯一 ID、asyncio.Task、可取消的 stop_event、最后活跃时间。"""

    __slots__ = ("id", "task", "stop_event", "last_active")

    def __init__(self, idx: int, task: asyncio.Task, stop_event: asyncio.Event):
        self.id = idx
        self.task = task
        self.stop_event = stop_event
        self.last_active = time.monotonic()


class Engine:
    def __init__(self, db):
        self.db = db
        limits = {
            0: config.ADMIN_QUEUE_MAX,
            1: config.HIGH_QUEUE_MAX,
            2: config.NORMAL_QUEUE_MAX,
        }
        self.queue: CountedPriorityQueue = CountedPriorityQueue(
            maxsize=sum(limits.values()), limits=limits)
        # 旧观测接口同步镜像：deadline 兼容 _queue_counts（CountedPriorityQueue 内部用
        # count() 为准）；put/get 在 submit_priority 与 _worker_loop 中手动同步递减。
        self._queue_counts = {0: 0, 1: 0, 2: 0}
        self._seq = 0  # 同优先级 FIFO 自增计数器
        self.token_pool_manager = TokenPoolManager(self)
        self.processing = 0          # 当前生成中的任务数（实时并发）
        self._started = False        # start() 后置真：池懒创建时才启动后台预取
        self._started_at = time.time()
        self._workers: list[_WorkerHandle] = []
        self._auto_scaler_task: asyncio.Task | None = None
        # S-4: 入队时刻表（task_id → monotonic），worker 取走时算 queue_ms；终态后清理
        self._enqueued_at: dict[str, float] = {}
        # ── 持久化队列（IMP-29）─────────────────────────
        self._persistent_queue = config.IF_PERSISTENT_QUEUE_ENABLED
        self._queue_db: QueueDB | None = None
        if self._persistent_queue:
            self._queue_db = QueueDB(config.IF_PERSISTENT_QUEUE_DB)

    # ── 生命周期 ──────────────────────────────────
    async def start(self) -> None:
        # H4: 回收上次进程遗留的孤儿任务（pending/processing 永不结束的）
        recovered = await self.db.recover_stale_tasks(stale_after=config.TASK_HARD_TIMEOUT + 60)
        if recovered:
            log.info("已回收 %d 条孤儿任务（上次进程遗留的 pending/processing）", recovered)
        self._started = True
        await self.token_pool_manager.start()
        self._workers = [self._create_worker(i)
                         for i in range(config.WORKERS)]
        if config.IF_WORKER_AUTO:
            self._auto_scaler_task = asyncio.create_task(self._auto_scale_loop())
        # ── 持久化队列恢复（IMP-29）─────────────────────
        if self._persistent_queue and self._queue_db:
            restored = self._resume_from_queue()
            log.info("持久化队列恢复: %d 个待消费任务续跑", restored)
        log.info("引擎启动: workers=%d token_pool=%d 队列上限=%d auto_scale=%s batch=%s",
                 config.WORKERS, config.TOKEN_POOL_SIZE, config.MAX_QUEUE,
                 config.IF_WORKER_AUTO, config.IF_WORKER_BATCH_ENABLED)

    async def stop(self) -> None:
        if self._auto_scaler_task:
            self._auto_scaler_task.cancel()
        await self.token_pool_manager.stop()
        for w in self._workers:
            w.stop_event.set()
            w.task.cancel()
        # MEDIUM-1: 等协程真正退出（含正在进行的 httpx 请求清理），再让调用方关连接池，
        # 避免 stream 半途被 aclose 引发 "Task exception was never retrieved" 噪声。
        tasks = [w.task for w in self._workers if w.task and not w.task.done()]
        if self._auto_scaler_task and not self._auto_scaler_task.done():
            tasks.append(self._auto_scaler_task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ── 入口 ──────────────────────────────────────
    async def submit(self, prompt: str, aspect_ratio: str, download: bool,
                     model: str = "default") -> str:
        """登记并入队（默认 normal 优先级）。队列满抛 QueueFull → 调用方回 429。"""
        return await self.submit_priority(prompt, aspect_ratio, download, model, priority=2)

    async def submit_priority(self, prompt: str, aspect_ratio: str, download: bool,
                              model: str = "default", priority: int = 2) -> str:
        """登记并入队（指定优先级）。队列满抛 QueueFull → 调用方回 429。

        priority: 0=admin, 1=paid, 2=normal。各级队列超过独立上限时返回 429。
        """
        task_id = str(uuid.uuid4())
        await self.db.create_request(task_id, prompt, aspect_ratio, download, "txt", model)
        limits = {0: config.ADMIN_QUEUE_MAX, 1: config.HIGH_QUEUE_MAX, 2: config.NORMAL_QUEUE_MAX}
        try:
            if config.IF_WORKER_BATCH_ENABLED and self.queue.is_full(priority):
                raise asyncio.QueueFull
            seq = self._next_seq()
            self.queue.put_nowait((priority, seq, task_id))
            self._queue_counts[priority] = self._queue_counts.get(priority, 0) + 1
            self._enqueued_at[task_id] = time.monotonic()
            # IMP-29: 持久化队列写入
            if self._persistent_queue and self._queue_db:
                self._queue_db.enqueue(task_id, priority, seq)
        except asyncio.QueueFull:
            await self.db.mark_finished(task_id, "error", None, "queue_full", None)
            raise QueueFull("服务器繁忙，请稍后重试")
        return task_id

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    async def requeue_dlq_task(self, task_id: str) -> bool:
        """S-9: DLQ 真重入队——把失败任务重置为 pending 并放回 normal 队列。

        仅当 IF_DLQ_REQUEUE=1 时由端点调用；队列满返回 False（记录保留在 DLQ）。
        """
        row = await self.db.get(task_id)
        if not row:
            return False
        await self.db.mark_pending_again(task_id)
        try:
            seq = self._next_seq()
            self.queue.put_nowait((2, seq, task_id))
            self._queue_counts[2] = self._queue_counts.get(2, 0) + 1
            self._enqueued_at[task_id] = time.monotonic()
        except asyncio.QueueFull:
            # 队列满：回滚状态标记，保持 error，让调用方决定
            await self.db.mark_finished(task_id, "error", None, "requeue_failed: queue_full", None)
            return False
        if self._persistent_queue and self._queue_db:
            self._queue_db.enqueue(task_id, 2, seq)
        log.info("DLQ 重入队: task %s 已放回 normal 队列", task_id)
        return True

    async def wait_result(self, task_id: str, timeout: float) -> dict:
        """同步接口：轮询直到终态或超时。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            t = await self.db.get(task_id)
            if t and t["status"] in ("completed", "error"):
                return t
            await asyncio.sleep(0.5)
        t = await self.db.get(task_id)
        if t is None:
            return {"id": task_id, "status": "error", "error": "查询失败",
                    "image_url": None, "image_base64": None, "image_mime": None,
                    "duration_sec": None, "type": "txt", "model": "default"}
        return t

    def _resume_from_queue(self) -> int:
        """持久化队列恢复：从 task_queue 读取 pending 任务，按 priority/seq 排序后重新入队。
        返回恢复的任务数。"""
        if not self._queue_db:
            return 0
        pending = self._queue_db.list_pending()
        if not pending:
            return 0
        for priority, seq, task_id in pending:
            try:
                self.queue.put_nowait((priority, seq, task_id))
            except asyncio.QueueFull:
                break
        return len(pending)

    # ── token 池（多 key 转发）──────────────────────
    @property
    def token_pool(self) -> asyncio.Queue:
        """兼容转发：healthz/metrics 用 engine.token_pool.qsize() 看 direct 池水位。"""
        return self.token_pool_manager.direct_queue()

    async def _acquire_token(self, timeout: float) -> str | None:
        """取 direct 池 token（_process 内部调用保持兼容）。"""
        return await self.token_pool_manager.acquire("direct", timeout)

    async def acquire_token(self, key: str = "direct",
                            timeout: float = config.TOKEN_WAIT_TIMEOUT) -> str | None:
        """公开入口：文生图直连取 "direct" 池；图生图代理模式传 key=代理 URL 取对应 per-proxy 池。"""
        return await self.token_pool_manager.acquire(key, timeout)

    # ── worker 池 ─────────────────────────────────
    def _create_worker(self, idx: int) -> _WorkerHandle:
        """创建唯一 worker 句柄：启动 _worker_loop 或 _worker_batch_loop 协程。"""
        stop_event = asyncio.Event()
        if config.IF_WORKER_BATCH_ENABLED:
            task = asyncio.create_task(self._worker_batch_loop(idx, stop_event))
        else:
            task = asyncio.create_task(self._worker_loop(idx, stop_event))
        # S-7: 同步心跳注册表（扩缩容增减时保持一致）
        worker_health.register([w.id for w in self._workers] + [idx])
        return _WorkerHandle(idx, task, stop_event)

    # ── 队列入队速率统计（P-04）─────────────────────
    async def queue_in_rate(self, window: float = 60.0) -> float:
        """P-04: 估算过去 window 秒内的平均入队速率（任务/秒）。

        基于 DB 中最近 window 秒内创建的 pending/completed 任务数。
        P-01 后 DB 为 aiosqlite 异步驱动，此处为异步版本。
        """
        try:
            count = await self.db.count_recent_requests(window)
            return count / window if count > 0 else 0.0
        except Exception:
            return 0.0

    # ── 批量 worker 循环（P-02）─────────────────────
    async def _worker_batch_loop(self, idx: int, stop_event: asyncio.Event | None = None) -> None:
        """P-02: 批量 worker 循环。批量从队列取任务，批量获取 token，并行处理。"""
        batch_size = config.IF_WORKER_BATCH_SIZE
        while True:
            if stop_event and stop_event.is_set():
                log.info("batch_worker[%d] 收到退出信号", idx)
                return
            # 批量取任务（最多 batch_size 个，超时 0.1s）
            tasks: list[tuple[int, int, str]] = []
            try:
                item = await asyncio.wait_for(self.queue.get(), timeout=0.1)
                tasks.append(item)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            # 尝试取更多任务（非阻塞，最多 batch_size）
            for _ in range(batch_size - 1):
                try:
                    item = self.queue.get_nowait()
                    tasks.append(item)
                except asyncio.QueueEmpty:
                    break
            # 更新 worker 活跃时间
            if self._workers:
                for w in self._workers:
                    if w.id == idx:
                        w.last_active = time.monotonic()
                        break
            worker_health.beat(idx)
            self.processing += len(tasks)
            # 并行处理
            try:
                async with asyncio.timeout(config.TASK_HARD_TIMEOUT):
                    results = await asyncio.gather(
                        *(self._process(tid) for _, _, tid in tasks),
                        return_exceptions=True,
                    )
                worker_health.add_processed(idx, len(tasks))
                for task_item, result in zip(tasks, results):
                    _, _, tid = task_item
                    if isinstance(result, asyncio.TimeoutError):
                        log.error("batch task %s 硬超时（%ss），强制回收", tid, config.TASK_HARD_TIMEOUT)
                        await self.db.mark_finished(tid, "error", None,
                                              f"生成硬超时（>{config.TASK_HARD_TIMEOUT}s）", None)
                        if self._persistent_queue and self._queue_db:
                            self._queue_db.mark_completed(tid)
                    elif isinstance(result, Exception):
                        log.exception("batch 任务执行异常 %s", tid)
                        await self.db.mark_finished(tid, "error", None, f"{result}", None)
                        if self._persistent_queue and self._queue_db:
                            self._queue_db.mark_completed(tid)
            except asyncio.TimeoutError:
                log.error("batch 整体硬超时（%ss），强制回收 %d 个任务",
                          config.TASK_HARD_TIMEOUT, len(tasks))
                for _, _, tid in tasks:
                    await self.db.mark_finished(tid, "error", None,
                                          f"批量生成硬超时（>{config.TASK_HARD_TIMEOUT}s）", None)
                    if self._persistent_queue and self._queue_db:
                        self._queue_db.mark_completed(tid)
            except asyncio.CancelledError:
                raise
            finally:
                self.processing -= len(tasks)
                for _ in tasks:
                    self.queue.task_done()

    async def _worker_loop(self, idx: int, stop_event: asyncio.Event | None = None) -> None:
        while True:
            if stop_event and stop_event.is_set():
                log.info("worker[%d] 收到退出信号", idx)
                return
            try:
                priority, seq, task_id = await asyncio.wait_for(
                    self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                log.info("worker[%d] 等待队列时被取消", idx)
                raise
            # 更新 worker 活跃时间
            if self._workers:
                for w in self._workers:
                    if w.id == idx:
                        w.last_active = time.monotonic()
                        break
            worker_health.beat(idx)
            self.processing += 1
            try:
                async with asyncio.timeout(config.TASK_HARD_TIMEOUT):
                    await self._process(task_id)
                worker_health.add_processed(idx)
            except asyncio.TimeoutError:
                log.error("task %s 硬超时（%ss），强制回收", task_id, config.TASK_HARD_TIMEOUT)
                await self.db.mark_finished(task_id, "error", None,
                                      f"生成硬超时（>{config.TASK_HARD_TIMEOUT}s）", None)
                if self._persistent_queue and self._queue_db:
                    self._queue_db.mark_completed(task_id)
            except asyncio.CancelledError:
                log.info("worker[%d] 任务执行中被取消，清理状态", idx)
                raise
            except Exception as e:
                log.exception("任务执行异常 %s", task_id)
                await self.db.mark_finished(task_id, "error", None, f"{e}", None)
                if self._persistent_queue and self._queue_db:
                    self._queue_db.mark_completed(task_id)
            finally:
                self.processing -= 1
                self._queue_counts[priority] = max(0, self._queue_counts.get(priority, 0) - 1)
                self.queue.task_done()

    # ── 自动伸缩（IMP-03）──────────────────────────
    async def _auto_scale_loop(self) -> None:
        """每 30s 检查一次，根据排队长度和空闲时间弹性增减 worker。"""
        while True:
            await asyncio.sleep(30)
            try:
                await self._auto_scale_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("自动伸缩异常: %s", e)

    async def _auto_scale_once(self) -> None:
        """单次伸缩检查（可被测试直接调用）。"""
        qsize = self.queue.qsize()
        current = len(self._workers)

        # 扩容：排队 > 阈值 且 未达上限 → 增 2 个（最多增 2 / 30s）
        if qsize > config.IF_WORKER_SCALE_UP_THRESHOLD and current < config.IF_WORKERS_MAX:
            target = min(current + 2, config.IF_WORKERS_MAX)
            added = target - current
            for _ in range(added):
                next_idx = max((w.id for w in self._workers), default=-1) + 1
                self._workers.append(self._create_worker(next_idx))
            log.info("自动扩容: %d → %d（排队 %d > %d）",
                     current, target, qsize, config.IF_WORKER_SCALE_UP_THRESHOLD)

        # 缩容：排队 < 阈值 或 空闲超阈值 → 缩 1 个（最多缩 1 / 30s）
        elif current > config.IF_WORKERS_MIN:
            should_shrink = False
            reason = ""
            if qsize < config.IF_WORKER_SCALE_DOWN_THRESHOLD:
                should_shrink = True
                reason = f"排队 {qsize} < {config.IF_WORKER_SCALE_DOWN_THRESHOLD}"
            elif self._idle_workers_count() >= 1:
                # 至少有 1 个空闲 worker
                idle_count = self._idle_workers_count()
                if idle_count >= 1:
                    should_shrink = True
                    reason = f"{idle_count} 个 worker 空闲超过 {config.IF_WORKER_IDLE_SECONDS}s"

            if should_shrink:
                self._shrink_one_worker()
                worker_health.register([w.id for w in self._workers])
                log.info("自动缩容: %d → %d（%s）",
                         current, len(self._workers), reason)

    def _idle_workers_count(self) -> int:
        """统计空闲超过 IF_WORKER_IDLE_SECONDS 的 worker 数。"""
        now = time.monotonic()
        idle_threshold = config.IF_WORKER_IDLE_SECONDS
        return sum(1 for w in self._workers
                   if now - w.last_active > idle_threshold)

    def _shrink_one_worker(self) -> None:
        """通知一个 worker 退出并移除。优先缩容最空闲的 worker。"""
        # 按空闲时间排序，取最空闲的
        if not self._workers:
            return
        self._workers.sort(key=lambda w: w.last_active)
        target = self._workers[0]
        target.stop_event.set()
        target.task.cancel()
        self._workers = [w for w in self._workers if w.id != target.id]
        log.info("缩容 worker[%d]", target.id)

    async def _process(self, task_id: str) -> None:
        row = await self.db.get(task_id)
        if not row:
            return
        await self.db.mark_started(task_id)
        # IMP-29: 持久化队列标记 processing
        if self._persistent_queue and self._queue_db:
            self._queue_db.mark_processing(task_id)
        t0 = time.monotonic()
        last_error: str | None = None
        # S-4: 慢日志画像阶段计时（queue_ms = worker 取走 → 开始处理）
        queue_ms = (t0 - self._enqueued_at.get(task_id, t0)) * 1000.0
        self._enqueued_at.pop(task_id, None)
        _slow = {"queue": queue_ms, "wait_token": 0.0, "solve": 0.0,
                 "upstream": 0.0, "retry": 0.0}
        # IMP-05: 使用统一 RetryPolicy 处理 transient 错误重试
        # IMP-08: 创建任务处理 span，trace_id 贯穿所有子操作
        tracer = get_tracer()
        with tracer.start_as_current_span(
            "worker.process",
            attributes={
                "task.id": task_id,
                "task.prompt_preview": (row.get("prompt") or "")[:60],
                "task.model": row.get("model", "default"),
                "task.aspect_ratio": row.get("aspect_ratio", "1:1"),
            },
        ):
            for attempt in range(1, config.IF_TXT_RETRY_MAX + 1):
                with tracer.start_as_current_span(
                    "worker.acquire_token",
                    attributes={"attempt": attempt},
                ):
                    _tk0 = time.monotonic()
                    token = await self._acquire_token(config.TOKEN_WAIT_TIMEOUT)
                    _slow["wait_token"] += (time.monotonic() - _tk0) * 1000.0
                if token is None:
                    # 熔断 OPEN 时 acquire 快速失败（非超时），文案要区分，避免排查误判成 30s 超时
                    last_error = ("求解熔断中，cf_solver 暂不可用，请稍后重试"
                                  if solver_guard.circuit_open
                                  else f"等待 turnstile token 超时（>{config.TOKEN_WAIT_TIMEOUT}s）")
                    break
                try:
                    with tracer.start_as_current_span(
                        "provider.submit",
                        attributes={
                            "attempt": attempt,
                            "task.model": row.get("model", "default"),
                        },
                    ):
                        _up0 = time.monotonic()
                        result = await self._generate_once(row, token)
                        _slow["upstream"] += (time.monotonic() - _up0) * 1000.0
                except Exception as e:
                    last_error = str(e)
                    if _is_token_rejected(e):
                        solver_guard.record_rejected()
                    # 判断是否应重试（transient 且 attempt < max）
                    if RetryPolicy.should_retry(attempt, config.IF_TXT_RETRY_MAX, e):
                        # token_rejected 会以更短退避重试（换新 token 大概率成功）
                        err_type = RetryPolicy.classify(e)
                        base = (1.0 if err_type == "token_rejected"
                                else config.IF_TXT_RETRY_BACKOFF_BASE)
                        delay = RetryPolicy.backoff_delay(attempt, base)
                        log.warning("task %s 第 %d/%d 次 transient 错误（%.80s），退避 %.1fs 后重试",
                                    task_id, attempt, config.IF_TXT_RETRY_MAX, e, delay)
                        _slow["retry"] += delay * 1000.0
                        await asyncio.sleep(delay)
                        continue
                    # permanent 错误或重试满 → 失败（标记 error 后继续到 DLQ 逻辑）
                    log.warning("task %s 第 %d/%d 次永久错误（%.80s），标记为失败",
                                task_id, attempt, config.IF_TXT_RETRY_MAX, e)
                    last_error = str(e)
                    break  # 跳出循环，继续到 DLQ 推送
                else:
                    await self._finish(task_id, "completed", result["image_url"], None, t0,
                                 result.get("image_base64"), result.get("image_mime"))
                    log.info("出图完成 %s 耗时 %.1fs", task_id, time.monotonic() - t0)
                    self._record_slow(task_id, row, _slow, t0, "completed")
                    return
            # 重试耗尽 → DLQ 标记
        dlq_note = f"（DLQ: 重试 {config.IF_TXT_RETRY_MAX} 次耗尽）"
        dlq_msg = f"{last_error}{dlq_note}" if last_error else f"重试 {config.IF_TXT_RETRY_MAX} 次耗尽"
        await self._finish(task_id, "error", None, dlq_msg, t0)
        self._record_slow(task_id, row, _slow, t0, "error")
        # IMP-21: 重试满后如有 DLQ 配置则推入死信队列
        if config.IF_DLQ_ENABLED:
            row = await self.db.get(task_id)
            model = (row.get("model") or "default") if row else "default"
            await self.db.push_dlq(task_id, model, last_error, config.IF_TXT_RETRY_MAX)
            log.info("DLQ: task %s 推入死信队列（model=%s, error=%s, attempts=%d）",
                     task_id, model, last_error, config.IF_TXT_RETRY_MAX)

    def _record_slow(self, task_id: str, row: dict, slow: dict, t0: float,
                     status: str) -> None:
        """S-4: 任务终态时提交慢日志画像（阈值内静默忽略）。"""
        try:
            slow_log.record(SlowSample(
                task_id=task_id,
                model=row.get("model", "default"),
                provider=row.get("model", "default").split("/", 1)[0] if row.get("model") else "imagefree",
                queue_ms=slow["queue"],
                wait_token_ms=slow["wait_token"],
                solve_ms=slow["solve"],
                upstream_ms=slow["upstream"],
                retry_ms=slow["retry"],
                total_ms=(time.monotonic() - t0) * 1000.0 + slow["queue"],
                status=status,
            ))
        except Exception as e:  # 画像失败绝不影响主流程
            log.debug("慢日志记录失败（可忽略）: %s", e)

    async def _finish(self, task_id: str, status: str, image_url: str | None,
                error: str | None, t0: float,
                image_base64: str | None = None, image_mime: str | None = None) -> None:
        """终态落库（统一累计耗时）。"""
        await self.db.mark_finished(task_id, status, image_url, error, time.monotonic() - t0,
                              image_base64, image_mime)
        # IMP-29: 持久化队列标记终态
        if self._persistent_queue and self._queue_db:
            self._queue_db.mark_completed(task_id)
        # IMP-11: 出图成功 → 失效画廊缓存，下次请求重新查询 DB
        # 使用懒导入避免循环依赖（worker → main → worker）
        try:
            from .main import broadcast_task_event
            broadcast_task_event(task_id, status, {"image_url": image_url, "error": error, "duration_sec": round(time.monotonic() - t0, 1)})
        except Exception:
            pass
        if status == "completed" and image_url:
            try:
                from .main import gallery_cache as _gc
                import asyncio
                asyncio.create_task(_gc.invalidate_prefix("gallery:"))
            except Exception as exc:
                log.warning("IMP-11 画廊缓存失效失败（可忽略）: %s", exc)

    async def _generate_once(self, row: dict, token: str) -> dict:
        """提交生成并轮询到出图。

        出图成功后若请求了 download，附带回 base64/mime；下载失败不影响出图结果
        （仍按 completed 返回 image_url，仅记录下载失败，HIGH-2）。
        """
        tid = await imagefree_client.submit_generate(
            config.BASE_URL, config.apply_model(row["prompt"], row.get("model", "default")),
            row["aspect_ratio"], token, 30.0,
        )
        result = await imagefree_client.poll_generate_status(
            config.BASE_URL, tid, config.GENERATE_TIMEOUT, config.GENERATE_POLL_INTERVAL,
        )
        out = {"status": "completed", "image_url": result["image"]}
        if row["download"]:
            try:
                raw = await imagefree_client.download_image(
                    result["image"], 60.0, config.MAX_IMAGE_BYTES,
                )
                # H8: 按字节魔数判定 mime，比 URL 后缀匹配可靠（上游可能返回 .webp/.avif）
                mime = imagefree_client.detect_mime(raw)
                out["image_base64"] = imagefree_client.to_base64(raw, mime)
                out["image_mime"] = mime
            except Exception as e:
                log.warning("图片下载失败（不影响出图结果）: %s", e)
        return out

    # ── 实时状态 ──────────────────────────────────
    def snapshot(self) -> dict:
        """当前并发 / 排队 / 队列上限 / 运行时长 / 各 token 池水位。"""
        return {
            "processing": self.processing,
            "queued": self.queue.qsize(),
            "queue_capacity": config.MAX_QUEUE,
            "workers": len(self._workers),
            "started_at": self._started_at,
            "uptime_seconds": int(time.time() - self._started_at),
            "token_pools": self.token_pool_manager.pools_snapshot(),
            "token_wait_timeout_total": self.token_pool_manager.wait_timeout_total,
        }
