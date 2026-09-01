"""api/sse_events.py TaskEventHub 单元测试（P0-2 覆盖率补强）。

覆盖：subscribe/unsubscribe、publish 广播 + 环形缓冲裁剪 + QueueFull 丢弃、
replay_after（None/-1/中途 id）、buffer_size/get_task_events/subscriber_count、
clear_task、publish_task_event（有 loop / 无 loop 两条路径）、await_pending_sse_tasks
（空集/正常/超时取消）、task_events_generator（Last-Event-ID 回放 + 终态断开 + 心跳）。
"""

from __future__ import annotations

import asyncio

import pytest

from api.sse_events import (
    MAX_QUEUE,
    TaskEventHub,
    _pending_sse_tasks,
    await_pending_sse_tasks,
    hub,
    publish_task_event,
    task_events_generator,
)


@pytest.fixture(autouse=True)
def _clean_hub():
    """每用例清空模块单例 hub 的内部状态（保持同一实例，避免双对象分叉）。"""
    hub._subscribers.clear()
    hub._buffers.clear()
    hub._seq = 0
    yield
    _pending_sse_tasks.clear()
    hub._subscribers.clear()
    hub._buffers.clear()


# ── 基础订阅/发布 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_subscribe_and_unsubscribe():
    h = TaskEventHub()
    q = await h.subscribe("t1")
    assert h.subscriber_count("t1") == 1
    await h.unsubscribe("t1", q)
    assert h.subscriber_count("t1") == 0
    # 重复 unsubscribe 不抛
    await h.unsubscribe("t1", q)


@pytest.mark.asyncio
async def test_publish_broadcasts_to_subscribers():
    h = TaskEventHub()
    q = await h.subscribe("t1")
    await h.publish("t1", "status", {"s": "pending"})
    payload = q.get_nowait()
    assert "event: status" in payload
    assert '"s": "pending"' in payload or '"s":"pending"' in payload.replace(" ", "")
    assert h.buffer_size("t1") == 1


@pytest.mark.asyncio
async def test_publish_no_subscribers_still_buffers():
    h = TaskEventHub()
    await h.publish("t2", "status", {})
    assert h.buffer_size("t2") == 1
    assert h.subscriber_count("t2") == 0


@pytest.mark.asyncio
async def test_publish_ring_buffer_capped():
    h = TaskEventHub()
    for i in range(60):
        await h.publish("t3", "progress", {"i": i})
    assert h.buffer_size("t3") == 50  # _MAX_EVENTS_PER_TASK


@pytest.mark.asyncio
async def test_publish_queue_full_dropped_not_blocked():
    h = TaskEventHub()
    q = await h.subscribe("t4")
    # 填满订阅队列
    for i in range(MAX_QUEUE + 5):
        await h.publish("t4", "progress", {"i": i})
    # 不抛异常；队列保持满
    assert q.qsize() == MAX_QUEUE
    assert h.buffer_size("t4") == 50


@pytest.mark.asyncio
async def test_event_ids_monotonic_across_tasks():
    h = TaskEventHub()
    await h.publish("a", "status", {})
    await h.publish("b", "status", {})
    await h.publish("a", "progress", {})
    events_a = h.get_task_events("a")
    ids = [e["id"] for e in events_a]
    assert ids[1] > ids[0] > 0
    assert h.get_task_events("b")[0]["id"] == ids[0] + 1


# ── replay_after（Last-Event-ID 补偿）────────────────────────


@pytest.mark.asyncio
async def test_replay_after_none_returns_all():
    h = TaskEventHub()
    await h.publish("t", "status", {})
    await h.publish("t", "result", {})
    events = await h.replay_after("t", None)
    assert [e.event for e in events] == ["status", "result"]


@pytest.mark.asyncio
async def test_replay_after_midstream():
    h = TaskEventHub()
    await h.publish("t", "status", {})
    all_events = await h.replay_after("t", None)
    mid_id = all_events[0].id
    await h.publish("t", "progress", {})
    events = await h.replay_after("t", mid_id)
    assert [e.event for e in events] == ["progress"]


@pytest.mark.asyncio
async def test_replay_after_unknown_task_empty():
    h = TaskEventHub()
    assert await h.replay_after("ghost", None) == []


# ── 快照与清理 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_task_events_flat_dict():
    h = TaskEventHub()
    await h.publish("t", "status", {"x": 1})
    events = h.get_task_events("t")
    assert set(events[0]) == {"id", "event", "data", "ts"}
    assert h.get_task_events("ghost") == []


@pytest.mark.asyncio
async def test_clear_task():
    h = TaskEventHub()
    await h.publish("t", "status", {})
    await h.clear_task("t")
    assert h.buffer_size("t") == 0


# ── publish_task_event（同步入口）─────────────────────────────


@pytest.mark.asyncio
async def test_publish_task_event_with_loop():
    publish_task_event("t-sync", "status", {"ok": 1})
    assert len(_pending_sse_tasks) == 1
    await asyncio.sleep(0.05)
    assert hub.buffer_size("t-sync") == 1
    await await_pending_sse_tasks()


def test_publish_task_event_without_loop_drops():
    """无运行 loop（同步上下文）→ 丢弃不抛。"""
    publish_task_event("t-noop", "status", {})  # pytest 同步函数无 loop


@pytest.mark.asyncio
async def test_await_pending_empty_returns_immediately():
    await await_pending_sse_tasks(timeout=0.1)  # 空集不抛不停


@pytest.mark.asyncio
async def test_await_pending_waits_and_clears():
    publish_task_event("t-wait", "status", {})
    assert len(_pending_sse_tasks) == 1
    await await_pending_sse_tasks(timeout=2.0)
    assert len(_pending_sse_tasks) == 0
    assert hub.buffer_size("t-wait") == 1


# ── task_events_generator ─────────────────────────────────────


class FakeRequest:
    """模拟 Starlette Request：headers + is_disconnected。"""

    def __init__(self, headers: dict | None = None, disconnect_after: int = 0):
        self.headers = headers or {}
        self._disconnect_after = disconnect_after
        self._reads = 0

    async def is_disconnected(self) -> bool:
        self._reads += 1
        return self._reads > self._disconnect_after


@pytest.mark.asyncio
async def test_generator_replays_last_event_id_then_live(monkeypatch):
    import api.sse_events as se

    monkeypatch.setattr(se, "HEARTBEAT_INTERVAL", 0.05)
    await hub.publish("tg1", "status", {"s": "pending"})
    await hub.publish("tg1", "progress", {"p": 50})
    all_ev = await hub.replay_after("tg1", None)
    last_id = all_ev[0].id  # 只回放第二条

    req = FakeRequest(headers={"Last-Event-ID": str(last_id)}, disconnect_after=3)
    chunks = [c async for c in task_events_generator("tg1", req)]
    joined = "".join(chunks)
    assert "event: progress" in joined  # Last-Event-ID 补偿回放
    assert "connected" in joined  # 初始连接确认


@pytest.mark.asyncio
async def test_generator_breaks_on_terminal_event(monkeypatch):
    import api.sse_events as se

    monkeypatch.setattr(se, "HEARTBEAT_INTERVAL", 0.05)
    req = FakeRequest(headers={}, disconnect_after=30)

    async def _publish_terminal():
        await asyncio.sleep(0.05)
        await hub.publish("tg2", "result", {"url": "x"})

    task = asyncio.create_task(_publish_terminal())
    chunks = [c async for c in task_events_generator("tg2", req)]
    await task
    joined = "".join(chunks)
    assert "event: result" in joined


@pytest.mark.asyncio
async def test_generator_invalid_last_event_id_ignored(monkeypatch):
    """Last-Event-ID 非数字 → 视为无补偿，全量回放。"""
    import api.sse_events as se

    monkeypatch.setattr(se, "HEARTBEAT_INTERVAL", 0.05)
    await hub.publish("tg3", "status", {})
    req = FakeRequest(headers={"Last-Event-ID": "not-a-number"}, disconnect_after=1)
    chunks = [c async for c in task_events_generator("tg3", req)]
    joined = "".join(chunks)
    assert "event: status" in joined  # 回放了全部历史


@pytest.mark.asyncio
async def test_generator_heartbeat_on_timeout(monkeypatch):
    """队列空闲超时 → 发心跳。"""
    import api.sse_events as se

    monkeypatch.setattr(se, "HEARTBEAT_INTERVAL", 0.05)
    req = FakeRequest(headers={}, disconnect_after=3)
    chunks = [c async for c in task_events_generator("tg4", req)]
    joined = "".join(chunks)
    assert '"heartbeat"' in joined.replace("'", '"')


@pytest.mark.asyncio
async def test_generator_disconnect_records_cancellation():
    """客户端断开 → finally 清理缓冲 + 取消计数。"""
    from api.sse_stats import sse_stats

    sse_stats.reset()
    req = FakeRequest(headers={}, disconnect_after=0)  # 立即断开
    chunks = [c async for c in task_events_generator("tg5", req)]
    assert any("connected" in c for c in chunks)
    snap = sse_stats.snapshot()
    assert snap["cancelled_subscriptions"] == 1
    assert snap["total_subscriptions"] == 1
