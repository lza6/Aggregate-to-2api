"""worker/queue.py — 队列与 worker 句柄的纯逻辑实体。

P0-4 从 engine.py 拆出：CountedPriorityQueue / QueueFull / _WorkerHandle /
_safe_proxy_label / _is_token_rejected / _TOKEN_REJECTED_MARKERS。

这些是 无 Engine 依赖 的纯类/函数，拆到独立模块便于复用与单测。
engine.py 顶层 re-export 保持旧 import 路径 `from api.worker.engine import
CountedPriorityQueue, QueueFull, _safe_proxy_label, _is_token_rejected` 可用。
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from urllib.parse import urlsplit

__all__ = [
    "CountedPriorityQueue",
    "QueueFull",
    "_WorkerHandle",
    "_is_token_rejected",
    "_safe_proxy_label",
    "_TOKEN_REJECTED_MARKERS",
]


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
