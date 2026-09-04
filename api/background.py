"""fire-and-forget 后台任务的强引用持有（v7.7 P1）。

asyncio 文档明确：事件循环仅持有 task 的弱引用，中途等待 I/O 的 task 可能被 GC
静默取消（表现：协程无声消失、告警丢失/封禁不落库/缓存不一致）。dispatch 的
_PROVIDER_TASKS 与 sse_events 的 _pending_sse_tasks 已各自维护强引用集合；本模块
把该模式收敛为通用工具，供零散的 create_task 调用点复用：

    from .background import spawn

    spawn(some_coro())          # 等价 asyncio.create_task，但持强引用 + 异常必记录

- 引用集为模块级 set，task 完成后 add_done_callback 自动 discard，无泄漏。
- 未捕获异常统一 log.exception（默认 create_task 只在 GC 时以
  "Future exception was never retrieved" 浮现，静默失败）。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

log = logging.getLogger(__name__)

_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def _done(t: asyncio.Task[Any]) -> None:
    _BACKGROUND_TASKS.discard(t)
    if not t.cancelled() and t.exception() is not None:
        log.exception("后台任务异常 %s", t, exc_info=t.exception())


def spawn(coro: Coroutine[Any, Any, Any], *, name: str | None = None) -> asyncio.Task[Any]:
    """创建后台任务并持强引用；异常必记录，不被 GC 静默吞掉。"""
    t = asyncio.create_task(coro, name=name)
    _BACKGROUND_TASKS.add(t)
    t.add_done_callback(_done)
    return t


def pending_count() -> int:
    """当前在途后台任务数（测试/诊断用）。"""
    return len(_BACKGROUND_TASKS)
