"""worker 心跳/卡死巡检（v3.1.0 S-7 / P-C6）：让「worker 卡死」可被发现。

每个 worker 循环取到任务时 beat() 续命；巡检 sweep() 标记超期未活跃的 worker 为
stale。纯内存 + 注入时钟（now_fn），测试无需真 sleep；与 IF_WORKER_AUTO 自适应
扩缩容正交（扩缩容管数量，本模块管健康）。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(slots=True)
class _WorkerState:
    wid: int
    last_active: float  # monotonic 时间戳
    processed: int = 0
    stale: bool = False


class WorkerHealthMonitor:
    """worker 心跳注册表：beat 续命 / sweep 巡检 / snapshot 诊断视图。

    stale_seconds: 超过该秒数无心跳即判 stale（默认 180s，> TASK_HARD_TIMEOUT 兜底）。
    """

    def __init__(self, stale_seconds: float = 180.0, now_fn=None):
        self._stale_seconds = stale_seconds
        # 默认真实单调时钟；测试注入 fake clock
        self._now = now_fn if now_fn is not None else time.monotonic
        self._workers: dict[int, _WorkerState] = {}
        # 保留 threading.Lock（非 asyncio.Lock）：所有方法为同步，操作纯内存 dict（微秒级），
        # 由 worker loop（async _worker_loop/_worker_batch_loop）经 beat/add_processed 调用。
        # 换 asyncio.Lock 会把 beat/register/sweep 传染成 async，而调用处是同步代码（_worker_loop
        # 内 worker_health.beat(idx) 同步调用）。asyncio 单线程事件循环无竞争零阻塞，此锁非阻塞源。
        self._lock = threading.Lock()

    def register(self, ids) -> None:
        """登记当前存活 worker 集合（引擎 start/扩缩容后调用）。"""
        with self._lock:
            known = set(ids)
            for wid in known:
                if wid not in self._workers:
                    self._workers[wid] = _WorkerState(wid=wid, last_active=self._now())
            for wid in list(self._workers):
                if wid not in known:
                    del self._workers[wid]

    def unregister(self, wid: int) -> None:
        with self._lock:
            self._workers.pop(wid, None)

    def beat(self, wid: int) -> None:
        """worker 活跃打点（取到任务/完成处理时调用）；未知 id 忽略。"""
        with self._lock:
            w = self._workers.get(wid)
            if w is not None:
                w.last_active = self._now()
                w.stale = False

    def add_processed(self, wid: int, n: int = 1) -> None:
        """累计该 worker 完成的任务数（观测用）。"""
        with self._lock:
            w = self._workers.get(wid)
            if w is not None:
                w.processed += n

    def sweep(self) -> list[int]:
        """巡检一轮：把超期未活跃的标记 stale，返回本轮新标记的 id 列表。"""
        now = self._now()
        newly: list[int] = []
        with self._lock:
            for w in self._workers.values():
                was_stale = w.stale
                w.stale = (now - w.last_active) > self._stale_seconds
                if w.stale and not was_stale:
                    newly.append(w.wid)
        return newly

    def snapshot(self) -> list[dict]:
        """逐 worker 健康明细（diagnostics 端点用）。"""
        now = self._now()
        with self._lock:
            workers = sorted(self._workers.values(), key=lambda w: w.wid)
            return [
                {
                    "id": w.wid,
                    "alive": not w.stale,
                    "stale": w.stale,
                    "last_active_monotonic": w.last_active,
                    "last_active_ago_seconds": round(now - w.last_active, 1),
                    "processed": w.processed,
                }
                for w in workers
            ]

    def summary(self) -> dict:
        """聚合摘要（前端健康卡用）。"""
        snap = self.snapshot()
        stale_ids = [w["id"] for w in snap if w["stale"]]
        return {
            "total": len(snap),
            "alive": len(snap) - len(stale_ids),
            "stale_count": len(stale_ids),
            "stale_ids": stale_ids,
        }


# ── 模块级单例（engine 与 diagnostics 共享）───────────────────────────
worker_health = WorkerHealthMonitor()
