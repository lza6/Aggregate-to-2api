"""每任务 SSE 事件流（TaskEventHub）+ Last-Event-ID 断线补偿。

v4.2 新增：与全局广播 /v1/events/tasks 不同，本模块提供**按任务**的事件流，
支持 status / progress / result / error / ping 标准事件类型，并带自增 event_id，
客户端断线重连可传 Last-Event-ID 头回放漏掉的事件（内存环形缓冲，不落盘）。

设计：
- TaskEventHub.subscribe(task_id) -> Queue：每任务独立订阅队列
- publish(task_id, event_type, data)：写入该任务的环形缓冲 + 广播给在订阅的队列
- 环形缓冲上限 _MAX_EVENTS_PER_TASK=50，防内存膨胀
- 线程安全：publish 可能来自 async worker 协程，用 asyncio.Lock（同 loop 内有效）
- 所有方法均为协程/线程安全，供 FastAPI 路由与 worker 同时调用
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

log = logging.getLogger("sse_events")

MAX_QUEUE = 50
_MAX_EVENTS_PER_TASK = 50
HEARTBEAT_INTERVAL = 15.0


def _sse_encode(event: str, data: dict, event_id: int) -> str:
    """标准 SSE 编码：event + id + data。"""
    return (
        f"id: {event_id}\n"
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


class StoredEvent:
    """环形缓冲中的一条历史事件（供 Last-Event-ID 回放）。"""
    __slots__ = ("id", "event", "data", "ts")

    def __init__(self, event_id: int, event: str, data: dict) -> None:
        self.id = event_id
        self.event = event
        self.data = data
        self.ts = time.time()


class TaskEventHub:
    """按任务的事件总线：每个 task_id 一个事件缓冲 + 一套订阅队列。"""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        # 缓冲条目的内部递增 id（全局单调，断线重连回放用）
        self._seq = 0
        self._buffers: dict[str, list[StoredEvent]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, task_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE)
        async with self._lock:
            self._subscribers.setdefault(task_id, []).append(q)
        return q

    async def unsubscribe(self, task_id: str, q: asyncio.Queue) -> None:
        async with self._lock:
            subs = self._subscribers.get(task_id)
            if subs:
                if q in subs:
                    subs.remove(q)
                if not subs:
                    del self._subscribers[task_id]

    async def publish(self, task_id: str, event: str, data: dict) -> None:
        """发布事件：写入该任务的历史缓冲 + 推给在订阅的所有队列。"""
        async with self._lock:
            self._seq += 1
            sid = self._seq
            buf = self._buffers.setdefault(task_id, [])
            buf.append(StoredEvent(sid, event, data))
            if len(buf) > _MAX_EVENTS_PER_TASK:
                del buf[: len(buf) - _MAX_EVENTS_PER_TASK]
            subs = list(self._subscribers.get(task_id, []))
        payload = _sse_encode(event, data, sid)
        for q in subs:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # 队列满：丢弃此条（客户端消费慢），但不阻塞发布
                pass

    async def replay_after(self, task_id: str, after_id: int | None) -> list[StoredEvent]:
        """返回该任务缓冲中 id>after_id 的所有事件（Last-Event-ID 回放）。"""
        if after_id is None:
            after_id = -1
        async with self._lock:
            buf = self._buffers.get(task_id) or []
            return [e for e in buf if e.id > after_id]

    def buffer_size(self, task_id: str) -> int:
        return len(self._buffers.get(task_id, []))

    def subscriber_count(self, task_id: str) -> int:
        return len(self._subscribers.get(task_id, []))

    async def clear_task(self, task_id: str) -> None:
        """任务终态后清理缓冲（防止长跑服务内存膨胀）。"""
        async with self._lock:
            self._buffers.pop(task_id, None)


# 模块级单例
hub = TaskEventHub()


async def task_events_generator(task_id: str, request) -> Any:
    """SSE 事件生成器：先回放历史（Last-Event-ID 补偿），再实时订阅，15s 心跳。

    终态事件 result/error 发出后自动断开。
    """
    # Last-Event-ID 断线补偿
    last_id = None
    raw = request.headers.get("Last-Event-ID")
    if raw and raw.isdigit():
        last_id = int(raw)
    for ev in await hub.replay_after(task_id, last_id):
        yield _sse_encode(ev.event, ev.data, ev.id)

    queue = await hub.subscribe(task_id)
    try:
        # 初始连接确认
        yield _sse_encode("ping", {"msg": "connected", "task_id": task_id}, -1)
        while True:
            if await request.is_disconnected():
                break
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)
            except asyncio.TimeoutError:
                yield _sse_encode("ping", {"msg": "heartbeat"}, -1)
                continue
            yield msg
            # 尝试解析事件类型，result/error → 结束流
            try:
                if '"event": "result"' in msg or '"event": "error"' in msg:
                    break
            except Exception:
                pass
    finally:
        await hub.unsubscribe(task_id, queue)
        await hub.clear_task(task_id)


def publish_task_event(task_id: str, event: str, data: dict) -> None:
    """供 async 环境同步调用的发布入口（内部自动包成 asyncio 任务执行）。"""
    try:
        asyncio.ensure_future(hub.publish(task_id, event, data))
    except RuntimeError:
        # 无运行中的 loop（测试/关闭期）→ 丢弃避免警告
        pass