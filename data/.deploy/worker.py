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
# 注意：solver_guard 模块内定义了同名单例实例，须导入实例本身（`from . import solver_guard`
# 会绑到模块对象，`solver_guard.allow_solve()` 将 AttributeError）。
from .solver_guard import solver_guard

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


class _TokenPool:
    """单个 key 的 token 池。

    key="direct" 为直连池（动态水位：无排队时维持 1 个新鲜 token，有排队补满 TOKEN_POOL_SIZE）；
    key=代理 URL 为 per-proxy 池（固定水位 EDIT_PROXY_POOL_SIZE，token 与出口代理 IP 绑定）。
    预取由 need_event 事件驱动（acquire 池空时置位立即唤醒）+ 1.0s 轮询兜底，替代原 sleep 轮询。
    """

    def __init__(self, key: str, target_getter, maxsize: int, idle_ttl: float,
                 proxy: str | None):
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
                    need = max(self.target_getter() - self.q.qsize(), 1)
                else:
                    need = self.target_getter() - self.q.qsize()
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
                        token = await turnstile_client.solve_turnstile(
                            config.CF_SOLVER_URL, config.BASE_URL, config.SITEKEY,
                            config.TURNSTILE_TIMEOUT, proxy=self.proxy)
                    if token and not self.q.full():
                        await self.q.put((token, time.time()))
                        # 注意：不刷新 last_activity——后台维持 token 不算「使用」，
                        # 否则代理池永远不算空闲、空闲回收失效。仅 acquire 成功时刷新。
                        self.need_event.clear()
                        # 单槽 cf_solver 求解 ~3s，成功后再等 1.5s 让槽释放，
                        # 避免连续补池触发 cf_solver 429 "Server penuh"（多调用方争抢单槽）
                        await asyncio.sleep(1.5)
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
            "target": self.target_getter(),
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
        """懒创建池。direct: 动态水位（无排队维持 1，有排队补满）；proxy: 固定水位、空闲回收 TTL。"""
        pool = self.pools.get(key)
        if pool is not None:
            # 引擎已启动但该池无 prefetch task（如启动前懒创建残留）→ 补启动，防 token 饥饿
            if self.engine._started and pool.task is None:
                pool.task = asyncio.create_task(pool.prefetch_loop())
            return pool
        if key == "direct":
            # 无排队任务时维持 1 个新鲜 token，避免满池空转重解；有排队补满（突发可用并发）
            pool = _TokenPool(
                key,
                lambda: (config.TOKEN_POOL_SIZE if self.engine.queue.qsize() > 0 else 1),
                config.TOKEN_POOL_SIZE,
                idle_ttl=float("inf"),   # direct 池不空闲回收
                proxy=None,
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


class Engine:
    def __init__(self, db):
        self.db = db
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=config.MAX_QUEUE)
        # 多 key token 池管理器：direct（直连）+ per-proxy（图生图代理出口 IP，token 绑定代理）
        self.token_pool_manager = TokenPoolManager(self)
        self.processing = 0          # 当前生成中的任务数（实时并发）
        self._started = False        # start() 后置真：池懒创建时才启动后台预取
        self._started_at = time.time()
        self._workers: list[asyncio.Task] = []

    # ── 生命周期 ──────────────────────────────────
    async def start(self) -> None:
        # H4: 回收上次进程遗留的孤儿任务（pending/processing 永不结束的）
        recovered = self.db.recover_stale_tasks()
        if recovered:
            log.info("已回收 %d 条孤儿任务（上次进程遗留的 pending/processing）", recovered)
        self._started = True
        await self.token_pool_manager.start()
        self._workers = [asyncio.create_task(self._worker_loop(i))
                         for i in range(config.WORKERS)]
        log.info("引擎启动: workers=%d token_pool=%d 队列上限=%d",
                 config.WORKERS, config.TOKEN_POOL_SIZE, config.MAX_QUEUE)

    async def stop(self) -> None:
        await self.token_pool_manager.stop()
        for t in self._workers:
            t.cancel()
        # MEDIUM-1: 等协程真正退出（含正在进行的 httpx 请求清理），再让调用方关连接池，
        # 避免 stream 半途被 aclose 引发 "Task exception was never retrieved" 噪声。
        tasks = [t for t in self._workers if t and not t.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ── 入口 ──────────────────────────────────────
    async def submit(self, prompt: str, aspect_ratio: str, download: bool,
                     model: str = "default") -> str:
        """登记并入队。队列满抛 QueueFull → 调用方回 429。"""
        task_id = str(uuid.uuid4())
        self.db.create_request(task_id, prompt, aspect_ratio, download, "txt", model)
        try:
            self.queue.put_nowait(task_id)
        except asyncio.QueueFull:
            # 入队失败：删掉刚插入的行，避免悬空
            self.db.mark_finished(task_id, "error", None, "queue_full", None)
            raise QueueFull("服务器繁忙，请稍后重试")
        return task_id

    async def wait_result(self, task_id: str, timeout: float) -> dict:
        """同步接口：轮询直到终态或超时。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            t = self.db.get(task_id)
            if t and t["status"] in ("completed", "error"):
                return t
            await asyncio.sleep(0.5)
        t = self.db.get(task_id)
        return t or {"id": task_id, "status": "error", "error": "查询失败"}

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
    async def _worker_loop(self, idx: int) -> None:
        while True:
            task_id = await self.queue.get()
            self.processing += 1
            try:
                await self._process(task_id)
            except Exception as e:
                log.exception("任务执行异常 %s", task_id)
                self.db.mark_finished(task_id, "error", None, f"{e}", None)
            finally:
                self.processing -= 1
                self.queue.task_done()

    async def _process(self, task_id: str) -> None:
        row = self.db.get(task_id)
        if not row:
            return
        self.db.mark_started(task_id)
        t0 = time.monotonic()
        last_error: str | None = None
        # token 被上游拒绝时换新 token 重试（最多 GENERATE_MAX_ATTEMPTS 次）。
        # token 一次性，每次尝试都从池里取一个全新的。
        for attempt in range(1, config.GENERATE_MAX_ATTEMPTS + 1):
            token = await self._acquire_token(config.TOKEN_WAIT_TIMEOUT)
            if token is None:
                # 熔断 OPEN 时 acquire 快速失败（非超时），文案要区分，避免排查误判成 30s 超时
                last_error = ("求解熔断中，cf_solver 暂不可用，请稍后重试"
                              if solver_guard.circuit_open
                              else f"等待 turnstile token 超时（>{config.TOKEN_WAIT_TIMEOUT}s）")
                break
            try:
                result = await self._generate_once(row, token)
            except Exception as e:
                last_error = str(e)
                if _is_token_rejected(e):
                    # 上游拒绝 token（换 token 信号）：独立计数，供健康趋势/审计
                    solver_guard.record_rejected()
                if attempt < config.GENERATE_MAX_ATTEMPTS and _is_token_rejected(e):
                    log.warning("task %s 第 %d 次提交被上游拒绝（token 失效），换 token 重试",
                                task_id, attempt)
                    continue
                if not _is_token_rejected(e):
                    # LOW-4: 未知文案采样，便于扩充拒绝标记集
                    log.debug("task %s 非 token 拒绝错误（新文案?）: %.160s", task_id, e)
                self._finish(task_id, "error", None, str(e), t0)
                return
            else:
                self._finish(task_id, "completed", result["image_url"], None, t0,
                             result.get("image_base64"), result.get("image_mime"))
                log.info("出图完成 %s 耗时 %.1fs", task_id, time.monotonic() - t0)
                return
        self._finish(task_id, "error", None, last_error, t0)

    def _finish(self, task_id: str, status: str, image_url: str | None,
                error: str | None, t0: float,
                image_base64: str | None = None, image_mime: str | None = None) -> None:
        """终态落库（统一累计耗时）。"""
        self.db.mark_finished(task_id, status, image_url, error, time.monotonic() - t0,
                              image_base64, image_mime)

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
            "workers": config.WORKERS,
            "started_at": self._started_at,
            "uptime_seconds": int(time.time() - self._started_at),
            "token_pools": self.token_pool_manager.pools_snapshot(),
        }
