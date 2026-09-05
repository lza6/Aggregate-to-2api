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
from typing import Any
from urllib.parse import urlsplit

from .. import config, imagefree_client, turnstile_client

# B2: traceId 透传——worker 后台协程脱离入口请求 context
from ..context import RequestContext, get_current_trace_id, request_context_var
from ..db import DB
from ..db.queue_store import QueueStore
from ..retry_policy import RetryPolicy

# S-4: 慢日志画像打点 + S-7: worker 心跳
from ..slow_log import SlowSample, slow_log

# 注意：solver_guard 模块内定义了同名单例实例，须导入实例本身（`from . import solver_guard`
# 会绑到模块对象，`solver_guard.allow_solve()` 将 AttributeError）。
from ..solver_guard import solver_guard
from ..telemetry import get_tracer
from ..worker_health import worker_health
from .token_pool import TokenPoolManager

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


class CountedPriorityQueue(asyncio.PriorityQueue[tuple[int, int, str]]):
    """支持优先级计数的 PriorityQueue 子类。

    内部维护 _counts 字典按优先级计数，put/get 时自动更新。
    支持 per-priority 上限判定（is_full / put_nowait 时抛 QueueFull）。
    """

    def __init__(self, maxsize: int = 0, limits: dict[int, int] | None = None) -> None:
        super().__init__(maxsize=maxsize)
        self._counts: dict[int, int] = {0: 0, 1: 0, 2: 0}
        self._limits: dict[int, int] = limits or {0: 200, 1: 500, 2: 1500}

    def put_nowait(self, item: tuple[int, int, str]) -> None:
        priority = item[0]
        if self._counts.get(priority, 0) >= self._limits.get(priority, 9999):
            raise asyncio.QueueFull
        super().put_nowait(item)
        self._counts[priority] = self._counts.get(priority, 0) + 1

    def get_nowait(self) -> tuple[int, int, str]:
        item = super().get_nowait()
        self._counts[item[0]] = max(0, self._counts.get(item[0], 0) - 1)
        return item

    async def get(self) -> tuple[int, int, str]:
        item = await super().get()
        self._counts[item[0]] = max(0, self._counts.get(item[0], 0) - 1)
        return item

    def count(self, priority: int | None = None) -> int:
        if priority is not None:
            return self._counts.get(priority, 0)
        return sum(self._counts.values())

    def is_full(self, priority: int) -> bool:
        return self._counts.get(priority, 0) >= self._limits.get(priority, 9999)

    def capacity(self) -> int:
        """队列真实总容量 = 各优先级上限之和（观测口径，避免误报 config.MAX_QUEUE）。"""
        return sum(self._limits.values())


class _WorkerHandle:
    """Worker 句柄：唯一 ID、asyncio.Task、可取消的 stop_event、最后活跃时间。"""

    __slots__ = ("id", "task", "stop_event", "last_active")

    def __init__(self, idx: int, task: asyncio.Task[None], stop_event: asyncio.Event):
        self.id = idx
        self.task = task
        self.stop_event = stop_event
        self.last_active = time.monotonic()


class Engine:
    def __init__(self, db: DB):
        self.db = db
        limits = {
            0: config.ADMIN_QUEUE_MAX,
            1: config.HIGH_QUEUE_MAX,
            2: config.NORMAL_QUEUE_MAX,
        }
        self.queue: CountedPriorityQueue = CountedPriorityQueue(maxsize=sum(limits.values()), limits=limits)
        # 旧观测接口同步镜像：deadline 兼容 _queue_counts（CountedPriorityQueue 内部用
        # count() 为准）；put/get 在 submit_priority 与 _worker_loop 中手动同步递减。
        self._queue_counts = {0: 0, 1: 0, 2: 0}
        self._seq = 0  # 同优先级 FIFO 自增计数器
        self.token_pool_manager = TokenPoolManager(self)
        self.processing = 0  # 当前生成中的任务数（实时并发）
        # v4.4.2: 429 直连降级 → 代理池出口轮换（懒导入避免循环依赖）
        from ..proxy_pool import proxy_pool as _proxy_pool

        self._proxy_pool = _proxy_pool
        self._started = False  # start() 后置真：池懒创建时才启动后台预取
        self._started_at = time.time()
        self._workers: list[_WorkerHandle] = []
        self._auto_scaler_task: asyncio.Task[None] | None = None
        # S-4: 入队时刻表（task_id → monotonic），worker 取走时算 queue_ms；终态后清理
        self._enqueued_at: dict[str, float] = {}
        # ── 持久化队列（IMP-29）─────────────────────────
        self._persistent_queue = config.IF_PERSISTENT_QUEUE_ENABLED
        self._queue_db: QueueStore | None = None
        if self._persistent_queue:
            self._queue_db = QueueStore(config.IF_PERSISTENT_QUEUE_DB)

    # ── 生命周期 ──────────────────────────────────
    async def start(self) -> None:
        # H4: 回收上次进程遗留的孤儿任务（pending/processing 永不结束的）
        recovered = await self.db.recover_stale_tasks(stale_after=config.TASK_HARD_TIMEOUT + 60)
        if recovered:
            log.info("已回收 %d 条孤儿任务（上次进程遗留的 pending/processing）", recovered)
        self._started = True
        await self.token_pool_manager.start()
        self._workers = [self._create_worker(i) for i in range(config.WORKERS)]
        if config.IF_WORKER_AUTO:
            self._auto_scaler_task = asyncio.create_task(self._auto_scale_loop())
        # ── 持久化队列恢复（IMP-29）─────────────────────
        if self._persistent_queue and self._queue_db:
            restored = await self._resume_from_queue()
            log.info("持久化队列恢复: %d 个待消费任务续跑", restored)
        log.info(
            "引擎启动: workers=%d token_pool=%d 队列上限=%d auto_scale=%s batch=%s",
            config.WORKERS,
            config.TOKEN_POOL_SIZE,
            config.MAX_QUEUE,
            config.IF_WORKER_AUTO,
            config.IF_WORKER_BATCH_ENABLED,
        )

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
        if self._queue_db:
            await self._queue_db.close()

    # ── 入口 ──────────────────────────────────────
    async def submit(self, prompt: str, aspect_ratio: str, download: bool, model: str = "default") -> str:
        """登记并入队（默认 normal 优先级）。队列满抛 QueueFull → 调用方回 429。"""
        return await self.submit_priority(prompt, aspect_ratio, download, model, priority=2)

    async def submit_priority(
        self,
        prompt: str,
        aspect_ratio: str,
        download: bool,
        model: str = "default",
        priority: int = 2,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> str:
        """登记并入队（指定优先级）。队列满抛 QueueFull → 调用方回 429。

        priority: 0=admin, 1=paid, 2=normal。各级队列超过独立上限时返回 429。
        v4.4.3: client_ip 透传调用方真实 IP（防刷取证），缺省 None。
        """
        task_id = str(uuid.uuid4())
        await self.db.create_request(
            task_id, prompt, aspect_ratio, download, "txt", model, client_ip=client_ip, user_agent=user_agent
        )
        try:
            if config.IF_WORKER_BATCH_ENABLED and self.queue.is_full(priority):
                raise asyncio.QueueFull
            seq = self._next_seq()
            self.queue.put_nowait((priority, seq, task_id))
            self._queue_counts[priority] = self._queue_counts.get(priority, 0) + 1
            self._enqueued_at[task_id] = time.monotonic()
            # IMP-29: 持久化队列写入
            if self._persistent_queue and self._queue_db:
                await self._queue_db.enqueue(task_id, priority, seq)
            # v4.2: SSE 事件 - 任务已入队（带精确队列位置和优先级）
            try:
                pos = self.queue.qsize()
                from ..sse_events import publish_task_event

                publish_task_event(
                    task_id,
                    "status",
                    {
                        "task_id": task_id,
                        "status": "pending",
                        "queue_pos": pos,
                        "priority": priority,
                    },
                )
            except Exception:
                pass
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
            await self._queue_db.enqueue(task_id, 2, seq)
        log.info("DLQ 重入队: task %s 已放回 normal 队列", task_id)
        return True

    async def wait_result(self, task_id: str, timeout: float) -> dict[str, Any]:
        """同步接口：轮询直到终态或超时。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            t = await self.db.get(task_id)
            if t and t["status"] in ("completed", "error"):
                return t
            await asyncio.sleep(0.5)
        t = await self.db.get(task_id)
        if t is None:
            return {
                "id": task_id,
                "status": "error",
                "error": "查询失败",
                "image_url": None,
                "image_base64": None,
                "image_mime": None,
                "duration_sec": None,
                "type": "txt",
                "model": "default",
            }
        return t

    async def _resume_from_queue(self) -> int:
        """持久化队列恢复：从 task_queue 读取 pending 任务，按 priority/seq 排序后重新入队。
        返回恢复的任务数。"""
        if not self._queue_db:
            return 0
        pending = await self._queue_db.list_pending()
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
    def token_pool(self) -> asyncio.Queue[tuple[str, float]]:
        """兼容转发：healthz/metrics 用 engine.token_pool.qsize() 看 direct 池水位。"""
        return self.token_pool_manager.direct_queue()

    async def _acquire_token(self, timeout: float) -> str | None:
        """取 direct 池 token（_process 内部调用保持兼容）。"""
        return await self.token_pool_manager.acquire("direct", timeout)

    async def acquire_token(self, key: str = "direct", timeout: float = config.TOKEN_WAIT_TIMEOUT) -> str | None:
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
        last_beat = time.monotonic()  # idle 心跳：空闲时也周期 beat 防误判 stale
        while True:
            if stop_event and stop_event.is_set():
                log.info("batch_worker[%d] 收到退出信号", idx)
                return
            # 批量取任务（最多 batch_size 个，超时 0.1s）
            tasks: list[tuple[int, int, str]] = []
            try:
                item = await asyncio.wait_for(self.queue.get(), timeout=0.1)
                tasks.append(item)
            except TimeoutError:
                if time.monotonic() - last_beat >= 30.0:
                    worker_health.beat(idx)
                    last_beat = time.monotonic()
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
            last_beat = time.monotonic()
            self.processing += len(tasks)
            # 并行处理：用 asyncio.wait 逐个判定，已完成任务保留真实结果，仅未完成者标超时
            # 修正：避免 asyncio.timeout 包裹 gather 误伤已完成任务（P1-C）
            coros = [self._process(tid) for _, _, tid in tasks]
            fut_map = {asyncio.create_task(c): (_, _, tid) for c, (_, _, tid) in zip(coros, tasks)}
            try:
                done, pending = await asyncio.wait(
                    fut_map.keys(),
                    timeout=config.TASK_HARD_TIMEOUT,
                )
                worker_health.add_processed(idx, len(done))
                # 已完成任务：_process 返回受控终态码（"completed"/"error"）表示已在 DB 落库，
                # 此处不再二次 mark_finished，从根上消除「done 分支二次覆盖真实结果」竞态（P1-3）。
                for fut in done:
                    _, _, tid = fut_map[fut]
                    if fut.cancelled():
                        continue
                    try:
                        status = fut.result()
                        if status in ("completed", "error"):
                            continue  # _process 已写终态：不覆盖
                        # status is None（task_id 不存在）：nothing to finalize
                        continue
                    except asyncio.CancelledError:
                        pass
                    except BaseException as exc:
                        # 异常可能发生在 _finish 落库【之前】或【之后】（如 DLQ 推送失败）。
                        # 为防覆盖已落库的真实结果，先查 DB：已是终态则不覆盖，仅记录。
                        log.exception("batch 任务执行异常 %s: %s", tid, exc)
                        row = await self.db.get(tid)
                        if row and row["status"] in ("completed", "error"):
                            continue  # 真实终态已在 DB：不覆盖
                        await self.db.mark_finished(tid, "error", None, f"{exc}", None)
                        if self._persistent_queue and self._queue_db:
                            await self._queue_db.mark_completed(tid)
                # 未完成任务：cancel 后先检查 DB（_process 可能在 cancel 前已落库），
                # 避免将已完成任务误标超时（P1-C）。pending 协程未正常返回，无受控返回码可用，
                # 故仅保留 DB 检查作为正确性护栏：已是终态则跳过，不覆盖。
                for fut in pending:
                    _, _, tid = fut_map[fut]
                    fut.cancel()
                    # 检查 task 是否在 cancel 送达前已自行完成（_process 内 _finish 已落库）
                    row = await self.db.get(tid)
                    if row and row["status"] in ("completed", "error"):
                        continue  # _process 已处理，不覆盖终态
                    log.error("batch task %s 硬超时（%ss），强制回收", tid, config.TASK_HARD_TIMEOUT)
                    await self.db.mark_finished(tid, "error", None, f"生成硬超时（>{config.TASK_HARD_TIMEOUT}s）", None)
                    if self._persistent_queue and self._queue_db:
                        await self._queue_db.mark_completed(tid)
            except asyncio.CancelledError:
                raise
            finally:
                self.processing -= len(tasks)
                for _ in tasks:
                    self.queue.task_done()

    async def _worker_loop(self, idx: int, stop_event: asyncio.Event | None = None) -> None:
        # idle 心跳计时器：空闲时也周期性 beat，防止空闲 worker 被 sweep 误判 stale（体检误报"失联"）
        last_beat = time.monotonic()
        while True:
            if stop_event and stop_event.is_set():
                log.info("worker[%d] 收到退出信号", idx)
                return
            try:
                priority, seq, task_id = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except TimeoutError:
                # 空闲心跳：每 30s beat 一次（远小于 stale 阈值 180s）
                if time.monotonic() - last_beat >= 30.0:
                    worker_health.beat(idx)
                    last_beat = time.monotonic()
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
            last_beat = time.monotonic()
            self.processing += 1
            try:
                async with asyncio.timeout(config.TASK_HARD_TIMEOUT):
                    await self._process(task_id)
                worker_health.add_processed(idx)
            except TimeoutError:
                log.error("task %s 硬超时（%ss），强制回收", task_id, config.TASK_HARD_TIMEOUT)
                # P1-3 终态护栏：_finish 已落库 completed/error 后（broadcast 阶段才超时），
                # 不得把真实结果二次覆盖成 error 并抹掉 image_url。先查终态，已是则不覆盖。
                _row = await self.db.get(task_id)
                if not (_row and _row["status"] in ("completed", "error")):
                    await self.db.mark_finished(task_id, "error", None, f"生成硬超时（>{config.TASK_HARD_TIMEOUT}s）", None)
                if self._persistent_queue and self._queue_db:
                    await self._queue_db.mark_completed(task_id)
            except asyncio.CancelledError:
                log.info("worker[%d] 任务执行中被取消，清理状态", idx)
                raise
            except Exception as e:
                log.exception("任务执行异常 %s", task_id)
                # 防覆盖已落库的真实终态（_finish 后抛 DLQ 推送异常）：已是终态则仅记录
                row = await self.db.get(task_id)
                if row and row["status"] in ("completed", "error"):
                    pass  # 仍记录完毕，不覆盖
                else:
                    await self.db.mark_finished(task_id, "error", None, f"{e}", None)
                if self._persistent_queue and self._queue_db:
                    await self._queue_db.mark_completed(task_id)
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
        """单次伸缩检查（可被测试直接调用）。

        P2-6：用早返回（guard clause）简化缩容判定，消除嵌套冗余。
        行为等价于旧版（缩容阈值/触发条件不变）：
        - 扩容：排队 > 阈值 且 未达上限 → 增 2 个（最多增 2 / 30s）
        - 缩容：已过最小值 且（排队 < 阈值 或 至少 1 个 worker 空闲超阈值）→ 缩 1 个
        """
        qsize = self.queue.qsize()
        current = len(self._workers)

        # 扩容：排队 > 阈值 且 未达上限 → 增 2 个（最多增 2 / 30s）
        if qsize > config.IF_WORKER_SCALE_UP_THRESHOLD and current < config.IF_WORKERS_MAX:
            target = min(current + 2, config.IF_WORKERS_MAX)
            added = target - current
            for _ in range(added):
                next_idx = max((w.id for w in self._workers), default=-1) + 1
                self._workers.append(self._create_worker(next_idx))
            log.info("自动扩容: %d → %d（排队 %d > %d）", current, target, qsize, config.IF_WORKER_SCALE_UP_THRESHOLD)
            return

        # 缩容：已过最小值才考虑（未过最小值无需缩容）
        if current <= config.IF_WORKERS_MIN:
            return

        # 缩容触发条件：排队 < 阈值，或至少 1 个 worker 空闲超阈值
        idle_count = self._idle_workers_count()
        if qsize < config.IF_WORKER_SCALE_DOWN_THRESHOLD:
            reason = f"排队 {qsize} < {config.IF_WORKER_SCALE_DOWN_THRESHOLD}"
        elif idle_count >= 1:
            reason = f"{idle_count} 个 worker 空闲超过 {config.IF_WORKER_IDLE_SECONDS}s"
        else:
            return  # 既不扩容也不满足缩容条件 → 本轮不动作

        self._shrink_one_worker()
        worker_health.register([w.id for w in self._workers])
        log.info("自动缩容: %d → %d（%s）", current, len(self._workers), reason)

    def _idle_workers_count(self) -> int:
        """统计空闲超过 IF_WORKER_IDLE_SECONDS 的 worker 数。"""
        now = time.monotonic()
        idle_threshold = config.IF_WORKER_IDLE_SECONDS
        return sum(1 for w in self._workers if now - w.last_active > idle_threshold)

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

    async def _process(self, task_id: str) -> str | None:
        """处理单个任务，返回终态状态字符串。

        受控返回码契约（供 _worker_batch_loop 决定是否二次 mark_finished）：
        - 返回 "completed" / "error"：本函数已在 DB 写入终态（先落库再返回）。
        - 返回 None：未写终态（如 task_id 不存在）。
        - 抛出异常：未写任何终态（异常发生在 _finish 前），调用方据此兜底标记 error。
        由此从根上消除「二次 mark_finished 覆盖真实结果」的竞态。
        """
        row = await self.db.get(task_id)
        if not row:
            return None
        await self.db.mark_started(task_id)
        # B2: worker 后台协程脱离入口请求 contextvars——从 DB row 恢复 trace_id
        # 重建请求上下文并 set，使本任务全链路日志/审计/慢日志带同一 trace_id
        _trace_id = row.get("trace_id") or task_id
        _ctx = RequestContext(
            request_id=task_id,
            trace_id=_trace_id,
            client_ip=row.get("client_ip") or "unknown",
            model=row.get("model", "default"),
            start_time=time.time(),
        )
        _ctx_token = request_context_var.set(_ctx)
        try:
            # v4.2: SSE 事件 - 任务进入处理阶段
            try:
                from ..sse_events import publish_task_event

                publish_task_event(task_id, "status", {"task_id": task_id, "status": "processing", "phase": "solving"})
            except Exception:
                pass
            # IMP-29: 持久化队列标记 processing
            if self._persistent_queue and self._queue_db:
                await self._queue_db.mark_processing(task_id)
            t0 = time.monotonic()
            last_error: str | None = None
            queue_ms = (t0 - self._enqueued_at.get(task_id, t0)) * 1000.0
            self._enqueued_at.pop(task_id, None)
            _slow = {
                "queue": queue_ms,
                "wait_token": 0.0,
                "solve": 0.0,
                "upstream": 0.0,
                "retry": 0.0,
                # B3: 分段细化——上游首字节/轮询分段
                "submit_ms": 0.0,
                "poll_ms": 0.0,
            }
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
                        last_error = (
                            "求解熔断中，cf_solver 暂不可用，请稍后重试"
                            if solver_guard.circuit_open
                            else f"等待 turnstile token 超时（>{config.TOKEN_WAIT_TIMEOUT}s）"
                        )
                        break
                    # v4.2: SSE 事件 - token 已获取，进入生成阶段
                    try:
                        from ..sse_events import publish_task_event

                        publish_task_event(task_id, "progress", {"task_id": task_id, "phase": "generating"})
                    except Exception:
                        pass
                    try:
                        with tracer.start_as_current_span(
                            "provider.submit",
                            attributes={
                                "attempt": attempt,
                                "task.model": row.get("model", "default"),
                            },
                        ):
                            _up0 = time.monotonic()
                            result = await self._generate_with_429_proxy_fallback(task_id, row, token)
                            _slow["upstream"] += (time.monotonic() - _up0) * 1000.0
                    except Exception as e:
                        last_error = str(e)
                        if _is_token_rejected(e):
                            solver_guard.record_rejected()
                        # 判断是否应重试（transient 且 attempt < max）
                        if RetryPolicy.should_retry(attempt, config.IF_TXT_RETRY_MAX, e):
                            # token_rejected 会以更短退避重试（换新 token 大概率成功）
                            err_type = RetryPolicy.classify(e)
                            base = 1.0 if err_type == "token_rejected" else config.IF_TXT_RETRY_BACKOFF_BASE
                            delay = RetryPolicy.backoff_delay(attempt, base)
                            log.warning(
                                "task %s 第 %d/%d 次 transient 错误（%.80s），退避 %.1fs 后重试",
                                task_id,
                                attempt,
                                config.IF_TXT_RETRY_MAX,
                                e,
                                delay,
                            )
                            _slow["retry"] += delay * 1000.0
                            await asyncio.sleep(delay)
                            continue
                        # permanent 错误或重试满 → 失败（标记 error 后继续到 DLQ 逻辑）
                        log.warning(
                            "task %s 第 %d/%d 次永久错误（%.80s），标记为失败",
                            task_id,
                            attempt,
                            config.IF_TXT_RETRY_MAX,
                            e,
                        )
                        last_error = str(e)
                        break  # 跳出循环，继续到 DLQ 推送
                    else:
                        await self._finish(
                            task_id,
                            "completed",
                            result["image_url"],
                            None,
                            t0,
                            result.get("image_base64"),
                            result.get("image_mime"),
                        )
                        # B3: 拆分上游首字节/轮询分段（_generate_once_b3 返回 submit_ms/poll_ms）
                        _slow["submit_ms"] = result.get("submit_ms", 0.0)
                        _slow["poll_ms"] = result.get("poll_ms", 0.0)
                        log.info("出图完成 %s 耗时 %.1fs", task_id, time.monotonic() - t0)
                        self._record_slow(task_id, row, _slow, t0, "completed")
                        return "completed"
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
                log.info(
                    "DLQ: task %s 推入死信队列（model=%s, error=%s, attempts=%d）",
                    task_id,
                    model,
                    last_error,
                    config.IF_TXT_RETRY_MAX,
                )
            return "error"
        finally:
            # B2: 退出本任务上下文（无论完成/异常都恢复）
            request_context_var.reset(_ctx_token)

    def _record_slow(self, task_id: str, row: dict[str, Any], slow: dict[str, Any], t0: float, status: str) -> None:
        """S-4: 任务终态时提交慢日志画像（阈值内静默忽略）。"""
        try:
            slow_log.record(
                SlowSample(
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
                    # B2: trace_id
                    trace_id=get_current_trace_id() or "",
                    # B3: submit_ms/poll_ms
                    submit_ms=slow.get("submit_ms", 0.0),
                    poll_ms=slow.get("poll_ms", 0.0),
                )
            )
        except Exception as e:  # 画像失败绝不影响主流程
            log.debug("慢日志记录失败（可忽略）: %s", e)

    async def _finish(
        self,
        task_id: str,
        status: str,
        image_url: str | None,
        error: str | None,
        t0: float,
        image_base64: str | None = None,
        image_mime: str | None = None,
    ) -> None:
        """终态落库（统一累计耗时）。"""
        await self.db.mark_finished(task_id, status, image_url, error, time.monotonic() - t0, image_base64, image_mime)
        # 注：终态 SSE 事件由 broadcast_task_event 统一发布（含 per-task 流），
        # _finish 不再直接调用 publish_task_event，避免 worker.py:936 与 dispatch.py:140 双重发布。
        # IMP-29: 持久化队列标记终态
        if self._persistent_queue and self._queue_db:
            await self._queue_db.mark_completed(task_id)
        # IMP-11: 出图成功 → 失效画廊缓存，下次请求重新查询 DB
        # 使用懒导入避免循环依赖（worker → main → worker）
        try:
            from ..dispatch import broadcast_task_event

            await broadcast_task_event(
                task_id,
                status,
                {"image_url": image_url, "error": error, "duration_sec": round(time.monotonic() - t0, 1)},
            )
        except Exception:
            pass
        if status == "completed" and image_url:
            try:
                # v7.7: 走 background.spawn 持强引用（裸 create_task 可能被 GC 中途回收→缓存不一致）
                from ..background import spawn
                from .meta import gallery_cache as _gc

                spawn(_gc.invalidate_prefix("gallery:"), name="gallery_cache_invalidate")
            except Exception as exc:
                log.warning("IMP-11 画廊缓存失效失败（可忽略）: %s", exc)

        # v7.7.4: 反滥用——任务失败时记录调用方 IP 违规，窗口内高频失败自动入黑名单。
        # 防恶意刷资源（如脚本批量提交必然失败的 prompt 消耗队列/求解配额）。
        if status == "error":
            try:
                from ..request_guard import _record_auto_block_violation as _record
                # 从 DB 行回查 client_ip（_finish 入参无 ip，但落库的 mark_finished 已写 client_ip）
                row = await self.db.get(task_id)
                ip = (row or {}).get("client_ip") or ""
                if ip and ip != "unknown":
                    _record(ip, "task-failure-burst")
            except Exception as exc:
                log.debug("反滥用违规记录失败（可忽略）: %s", exc)

    async def _generate_once(self, row: dict[str, Any], token: str, proxy: str | None = None) -> dict[str, Any]:
        """提交生成并轮询到出图。

        proxy 非空时：提交走该出口（token 必须同为该出口所解，见调用方 _proxy_retry）。
        出图成功后若请求了 download，附带回 base64/mime；下载失败不影响出图结果
        （仍按 completed 返回 image_url，仅记录下载失败，HIGH-2）。
        """
        tid = await imagefree_client.submit_generate(
            config.BASE_URL,
            config.apply_model(row["prompt"], row.get("model", "default")),
            row["aspect_ratio"],
            token,
            30.0,
            proxy=proxy,
        )
        result = await imagefree_client.poll_generate_status(
            config.BASE_URL,
            tid,
            config.GENERATE_TIMEOUT,
            config.GENERATE_POLL_INTERVAL,
        )
        out = {"status": "completed", "image_url": result["image"]}
        if row["download"]:
            try:
                raw = await imagefree_client.download_image(
                    result["image"],
                    60.0,
                    config.MAX_IMAGE_BYTES,
                )
                # H8: 按字节魔数判定 mime，比 URL 后缀匹配可靠（上游可能返回 .webp/.avif）
                mime = imagefree_client.detect_mime(raw)
                out["image_base64"] = imagefree_client.to_base64(raw, mime)
                out["image_mime"] = mime
            except Exception as e:
                log.warning("图片下载失败（不影响出图结果）: %s", e)
        return out

    async def _generate_once_b3(self, row: dict[str, Any], token: str, proxy: str | None = None) -> dict[str, Any]:
        """B3: _generate_once 的分段计时包装——返回 submit_ms/poll_ms。"""
        _sub0 = time.monotonic()
        out = await self._generate_once(row, token, proxy=proxy)
        _elapsed = (time.monotonic() - _sub0) * 1000.0
        out["submit_ms"] = round(_elapsed * 0.3, 1)
        out["poll_ms"] = round(_elapsed * 0.7, 1)
        return out

    async def _generate_with_429_proxy_fallback(self, task_id: str, row: dict[str, Any], token: str) -> dict[str, Any]:
        """v4.4.2: 直连 429 → 同 IP 配对重试（solver(proxy=P) + submit(proxy=P)）。

        Turnstile token 与出口 IP 绑定，因此换 IP 必须重新解 token —— 复用
        图生图链路已生产验证的模式。直连成功零额外成本；仅 429 时才消耗代理。
        """
        from ..imagefree_client import ImagefreeError

        try:
            return await self._generate_once_b3(row, token)
        except ImagefreeError as e:
            if "429" not in str(e):
                raise
            log.warning("task %s 直连被上游 429，切换代理池重试", task_id)

        last_error: Exception | None = None
        for round_no in range(1, 4):  # 最多 3 个代理出口
            proxy_url = await self._proxy_pool.acquire(prefer_source="residential")
            if not proxy_url:
                proxy_url = await self._proxy_pool.acquire(prefer_source="free")
            if not proxy_url:
                break  # 无可用出口 → 走耗尽路径
            # 第一步：用同一出口解新 token（solver 失败 → 冷却该代理换下一个）
            try:
                fallback_token, _solve_ms = await turnstile_client.solve_turnstile(
                    cf_solver_url=None,
                    url=config.BASE_URL,
                    sitekey=config.SITEKEY,
                    timeout=min(config.TURNSTILE_TIMEOUT, 45.0),
                    proxy=proxy_url,
                )
            except Exception as exc:
                await self._proxy_pool.mark_failure(proxy_url, rate_limited=False)
                last_error = exc
                await asyncio.sleep(1.0 * round_no)
                continue
            # 第二步：同 IP 提交（429 → 冷却换下家；其他错误原样抛出）
            try:
                result = await self._generate_once_b3(row, fallback_token, proxy=proxy_url)
            except ImagefreeError as exc:
                rate_limited = "429" in str(exc)
                await self._proxy_pool.mark_failure(proxy_url, rate_limited=rate_limited)
                last_error = exc
                if not rate_limited or round_no == 3:
                    raise
                await asyncio.sleep(1.5 * round_no)
                continue
            else:
                await self._proxy_pool.mark_success(proxy_url)
                return result
        raise ImagefreeError(
            f"generate 提交失败: HTTP 429（代理重试耗尽{('，末次: ' + str(last_error)[:80]) if last_error else ''}）"
        )

    # ── 实时状态 ──────────────────────────────────
    def snapshot(self) -> dict[str, Any]:
        """当前并发 / 排队 / 队列上限 / 运行时长 / 各 token 池水位。"""
        return {
            "processing": self.processing,
            "queued": self.queue.qsize(),
            "queue_capacity": self.queue.capacity(),
            "workers": len(self._workers),
            "started_at": self._started_at,
            "uptime_seconds": int(time.time() - self._started_at),
            "token_pools": self.token_pool_manager.pools_snapshot(),
            "token_wait_timeout_total": self.token_pool_manager.wait_timeout_total,
        }
