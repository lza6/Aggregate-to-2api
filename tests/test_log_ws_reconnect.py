"""M5-E1 补测：log_ws 断连重连与广播失败自愈。

覆盖 api/log_ws.py 缺失行（register_ws/unregister_ws/broadcast_log/_broadcast/WsLogHandler）：
- register_ws/unregister_ws 订阅集合增删
- broadcast_log 在有/无事件循环时的行为（不抛错）
- _broadcast 发送失败自动移除死连接
- WsLogHandler.emit 异常兜底（handleError 不外泄）
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from api.log_ws import (
    LogBuffer,
    WsLogHandler,
    _broadcast,
    _ws_subscribers,
    broadcast_log,
    register_ws,
    unregister_ws,
)


class _FakeWS:
    """轻量假 WebSocket：可控 send_json 成功/失败。"""

    def __init__(self, *, fail: bool = False):
        self.accepted = False
        self.sent: list[dict] = []
        self.fail = fail

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        if self.fail:
            raise ConnectionError("peer closed")
        self.sent.append(payload)


@pytest.fixture(autouse=True)
def _clean_subscribers():
    """每用例清空订阅者集合，避免跨用例污染。"""
    _ws_subscribers.clear()
    yield
    _ws_subscribers.clear()


@pytest.mark.asyncio
async def test_register_and_unregister_ws():
    """register_ws 接受连接并加入集合；unregister_ws 移除。"""
    ws = _FakeWS()
    await register_ws(ws)
    assert ws.accepted is True
    assert ws in _ws_subscribers
    await unregister_ws(ws)
    assert ws not in _ws_subscribers


@pytest.mark.asyncio
async def test_unregister_unknown_ws_is_idempotent():
    """移除不在集合中的连接不报错。"""
    ws = _FakeWS()
    # 未注册直接移除
    await unregister_ws(ws)
    assert ws not in _ws_subscribers


@pytest.mark.asyncio
async def test_broadcast_removes_dead_subscribers():
    """发送失败的连接在广播后自动移除（自愈断连）。"""
    alive = _FakeWS()
    dead = _FakeWS(fail=True)
    _ws_subscribers.add(alive)
    _ws_subscribers.add(dead)

    await _broadcast({"level": "INFO", "message": "ping"})
    # dead 被移除，alive 收到
    assert dead not in _ws_subscribers
    assert alive in _ws_subscribers
    assert alive.sent[-1]["message"] == "ping"


@pytest.mark.asyncio
async def test_broadcast_to_empty_subscribers_noop():
    """无订阅者时广播不抛错。"""
    _ws_subscribers.clear()
    await _broadcast({"level": "INFO", "message": "x"})
    assert _ws_subscribers == set()


def test_broadcast_log_no_running_loop_skips():
    """无运行事件循环时 broadcast_log 静默跳过（非异步线程不报错）。"""
    # 同步上下文调用，get_event_loop 可能抛 RuntimeError → 被捕获
    record = logging.LogRecord("t", logging.INFO, "t.py", 1, "msg", None, None)
    # 不应抛异常
    broadcast_log(record)


def test_broadcast_log_with_running_loop_schedules_coro():
    """有运行中的事件循环时 broadcast_log 调度 _broadcast 协程。"""

    async def _runner():
        ws = _FakeWS()
        _ws_subscribers.add(ws)
        record = logging.LogRecord("t", logging.INFO, "t.py", 1, "hello", None, None)
        broadcast_log(record)
        # 协程已调度但未必执行完，让事件循环跑一下
        await asyncio.sleep(0.05)
        assert ws.sent  # 收到广播
        _ws_subscribers.discard(ws)

    asyncio.run(_runner())


def test_ws_handler_emit_swallows_exception(monkeypatch):
    """WsLogHandler.emit 内部异常走 handleError，不外泄。"""
    handler = WsLogHandler()
    record = logging.LogRecord("t", logging.ERROR, "t.py", 1, "boom", None, None)

    # 让 broadcast_log 抛错（模拟 get_event_loop 异常路径外的真实失败）
    def _boom(_record):
        raise RuntimeError("simulated broadcast failure")

    monkeypatch.setattr("api.log_ws.broadcast_log", _boom)
    # 不应抛出
    handler.emit(record)


def test_ws_handler_emit_formats_record():
    """WsLogHandler.emit 调用 format 并广播（正常路径）。"""
    handler = WsLogHandler()
    record = logging.LogRecord("t", logging.WARNING, "t.py", 1, "warn msg", None, None)
    handler.emit(record)
    # format 应已设置 asctime 属性
    assert hasattr(record, "asctime")


def test_log_buffer_snapshot_returns_last_n():
    """snapshot(lines) 返回最近 N 条且倒序正确。"""
    buf = LogBuffer(maxlen=100)
    for i in range(10):
        buf.push({"i": i})
    snap = buf.snapshot(lines=3)
    assert [e["i"] for e in snap] == [7, 8, 9]


def test_log_buffer_snapshot_more_than_available():
    """请求行数超过实际时返回全部。"""
    buf = LogBuffer(maxlen=100)
    buf.push({"i": 1})
    buf.push({"i": 2})
    snap = buf.snapshot(lines=50)
    assert len(snap) == 2
