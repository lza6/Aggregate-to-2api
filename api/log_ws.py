"""WebSocket 实时日志推送 + 日志缓冲区。

通过 WebSocket 向客户端推送实时日志，支持 LogBuffer 收集最近日志。
日志处理器（WsLogHandler）注入 root logger，任何模块的日志自动广播到
所有已连接的 WebSocket 客户端，实现实时日志观测。

U-02: 实时日志推送 — 前端可 WebSocket 连接 /v1/logs/ws 接收实时日志流。
O-04: 深度可观测性 — 日志 + 指标 + 追踪联动。
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque

from fastapi import WebSocket

log = logging.getLogger("imagefree_api.log_ws")


class LogBuffer:
    """线程安全日志缓冲区。

    push 添加条目，snapshot 获取最近 N 条。线程安全（仅 Python 的 deque.append
    是原子的，但 snapshot 加列表拷贝确保一致性）。
    """

    def __init__(self, maxlen: int = 1000):
        self._buffer: deque[dict] = deque(maxlen=maxlen)

    def push(self, entry: dict) -> None:
        self._buffer.append(entry)

    def snapshot(self, lines: int = 50) -> list[dict]:
        return list(self._buffer)[-lines:]


_ws_subscribers: set[WebSocket] = set()
_ws_lock = asyncio.Lock()


async def register_ws(ws: WebSocket) -> None:
    """接受 WebSocket 连接并加入订阅者集合。"""
    await ws.accept()
    async with _ws_lock:
        _ws_subscribers.add(ws)


async def unregister_ws(ws: WebSocket) -> None:
    """从订阅者集合移除 WebSocket 连接。"""
    async with _ws_lock:
        _ws_subscribers.discard(ws)


def broadcast_log(record: logging.LogRecord) -> None:
    """广播日志到所有 WebSocket 订阅者。

    从 logging.Handler.emit 调用（非异步上下文），需要将异步广播任务
    调度到事件循环中执行。如果当前没有事件循环正在运行，跳过（避免
    在非异步线程中静默失败）。
    """
    entry = {
        "timestamp": getattr(record, "asctime", ""),
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage(),
    }
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(_broadcast(entry), loop)
    except RuntimeError:
        pass


async def _broadcast(entry: dict) -> None:
    """向所有订阅者发送 JSON 日志条目。发送失败的连接自动移除。"""
    dead: list[WebSocket] = []
    async with _ws_lock:
        for ws in list(_ws_subscribers):
            try:
                await ws.send_json(entry)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _ws_subscribers.discard(ws)


class WsLogHandler(logging.Handler):
    """将日志注入 WebSocket 广播的 Logging Handler。

    注入到 root logger 后，所有模块的日志都会通过广播传递给前端。
    """

    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter("%(asctime)s", datefmt="%Y-%m-%d %H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.format(record)
            broadcast_log(record)
        except Exception:
            self.handleError(record)


# 全局 WebSocket 日志处理器单例，供 main.py 注入日志系统
ws_log_handler = WsLogHandler()