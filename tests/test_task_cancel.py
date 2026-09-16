"""P0-4: 任务幂等取消 + 一键重试 + 阶段进度事件 测试。

覆盖契约：
- (a) pending/processing → cancel 200 终态 cancelled
- (b) 幂等两连 cancel 均 200 且状态机不落不一致
- (c) 已完成/失败任务 cancel 200 幂等不变态
- (d) 不存在 404；开关 IF_TASK_CANCEL_ENABLED=0 → 403 禁用
- (e) retry 返回新 task_id 且新任务进入队列（DB pending + 内存队列）
- 阶段进度事件：queued=5 / cancelled=100 status_detail/progress append-only 埋点

走 conftest 既有 fixture（tmp_db / monkeypatch），直接调用路由处理函数，不启真实网络。
"""

from __future__ import annotations

import asyncio

import pytest
from starlette.requests import Request

from api.db import DB
from api.errors import AppError
from api.routes.tasks import cancel_task, retry_task
from api.sse_events import hub
from api.worker import Engine


def _make_request() -> Request:
    """构造一个最小可用的 starlette Request（供 retry 的 _prepare/guard 消费）。"""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/tasks/x/retry",
        "headers": [(b"user-agent", b"test-agent")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
        "state": {},
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _clear_hub():
    """每用例清空模块单例 hub（与 test_sse_events_unit 同策略）。"""
    hub._subscribers.clear()
    hub._buffers.clear()
    hub._seq = 0
    yield
    hub._subscribers.clear()
    hub._buffers.clear()


@pytest.fixture
def eng(tmp_db, monkeypatch):
    """真实 Engine 绑定临时 DB + 关闭持久化队列（防连真实 data/queue.db），挂到 meta/dispatch。

    routes.tasks 的 db（顶部 `from ..meta import db`）与 dispatch 的 db/engine
    （顶部 `from .meta import db, engine`）均为 import 期绑定，须逐个 patch。
    """
    monkeypatch.setattr("api.config.IF_PERSISTENT_QUEUE_ENABLED", False)
    e = Engine(tmp_db)
    monkeypatch.setattr("api.meta.engine", e)
    monkeypatch.setattr("api.dispatch.engine", e)
    monkeypatch.setattr("api.dispatch.db", tmp_db)
    monkeypatch.setattr("api.routes.tasks.db", tmp_db)
    return e


async def _create(tmp_db: DB, task_id: str = "task-1", status: str = "pending") -> None:
    """建一条任务记录（默认 pending；支持 processing/completed/error 终态预置）。"""
    await tmp_db.create_request(task_id, "a cute cat", "1:1", True, "txt", "imagefree/default")
    if status == "processing":
        await tmp_db.mark_started(task_id)
    elif status == "completed":
        await tmp_db.mark_finished(task_id, "completed", "https://img.example/x.png", None, 1.0)
    elif status == "error":
        await tmp_db.mark_finished(task_id, "error", None, "boom", 1.0)


# ── (a) pending/processing → cancelled ────────────────────────


@pytest.mark.asyncio
async def test_cancel_pending_to_cancelled(tmp_db, eng):
    await _create(tmp_db, "t-cancel-pending")
    resp = await cancel_task("t-cancel-pending")
    assert resp == {"task_id": "t-cancel-pending", "status": "cancelled", "cancelled": True}
    row = await tmp_db.get("t-cancel-pending")
    assert row["status"] == "cancelled"
    assert row["finished_at"] is not None  # 落库终态时间


@pytest.mark.asyncio
async def test_cancel_processing_to_cancelled(tmp_db, eng):
    await _create(tmp_db, "t-cancel-proc", status="processing")
    resp = await cancel_task("t-cancel-proc")
    assert resp["status"] == "cancelled"
    assert resp["cancelled"] is True
    assert (await tmp_db.get("t-cancel-proc"))["status"] == "cancelled"


# ── (b) 幂等两连 cancel ──────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_idempotent_double(tmp_db, eng):
    await _create(tmp_db, "t-cancel-double")
    first = await cancel_task("t-cancel-double")
    second = await cancel_task("t-cancel-double")
    # 两次均 200（不抛 4xx/5xx）
    assert first["status"] == "cancelled" and first["cancelled"] is True
    assert second["status"] == "cancelled" and second["cancelled"] is False  # 幂等命中
    # 状态机不落不一致：终态保持 cancelled，且第二次不覆盖 finished_at/duration
    row = await tmp_db.get("t-cancel-double")
    assert row["status"] == "cancelled"
    assert row["finished_at"] is not None
    assert row["duration_sec"] is None  # cancel 不产生 duration（第二次也未写入）


# ── (c) 已完成/失败任务 cancel 幂等不变态 ─────────────────────


@pytest.mark.asyncio
async def test_cancel_completed_idempotent(tmp_db, eng):
    await _create(tmp_db, "t-cancel-done", status="completed")
    resp = await cancel_task("t-cancel-done")
    assert resp["status"] == "completed"
    assert resp["cancelled"] is False
    row = await tmp_db.get("t-cancel-done")
    assert row["status"] == "completed"  # 终态不被破坏
    assert row["image_url"] == "https://img.example/x.png"


@pytest.mark.asyncio
async def test_cancel_error_idempotent(tmp_db, eng):
    await _create(tmp_db, "t-cancel-err", status="error")
    resp = await cancel_task("t-cancel-err")
    assert resp["status"] == "error"
    assert resp["cancelled"] is False
    assert (await tmp_db.get("t-cancel-err"))["status"] == "error"


# ── (d) 404 / 403 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_not_found_404(tmp_db, eng):
    with pytest.raises(AppError) as ei:
        await cancel_task("t-ghost")
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_cancel_disabled_403(tmp_db, eng, monkeypatch):
    monkeypatch.setattr("api.config.IF_TASK_CANCEL_ENABLED", False)
    await _create(tmp_db, "t-cancel-off")
    with pytest.raises(AppError) as ei:
        await cancel_task("t-cancel-off")
    assert ei.value.status_code == 403
    # 未动任务状态（开关关闭不产生副作用）
    assert (await tmp_db.get("t-cancel-off"))["status"] == "pending"


# ── (e) 一键重试 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_returns_new_task_queued(tmp_db, eng):
    # L4（审查）：仅失败/已取消终态可重试（completed 重试 → 400，另有用例覆盖）
    await _create(tmp_db, "t-retry-src", status="error")
    resp = await retry_task(_make_request(), "t-retry-src")
    new_id = resp["task_id"]
    assert new_id != "t-retry-src"  # 新 task_id
    assert resp["source_task_id"] == "t-retry-src"
    assert resp["status"] == "queued"
    # 新任务进入 DB 且 pending，参数从原任务复制
    row = await tmp_db.get(new_id)
    assert row is not None
    assert row["status"] == "pending"
    assert row["prompt"] == "a cute cat"
    assert row["aspect_ratio"] == "1:1"
    assert row["download"] == 1
    assert row["model"] == "default"  # imagefree 路径存短名
    # 进入内存队列
    assert eng.queue.qsize() >= 1


@pytest.mark.asyncio
async def test_retry_not_found_404(tmp_db, eng):
    with pytest.raises(AppError) as ei:
        await retry_task(_make_request(), "t-ghost")
    assert ei.value.status_code == 404


# ── worker 感知取消（_process 检查点）──────────────────────


@pytest.mark.asyncio
async def test_worker_process_abandons_cancelled_task(tmp_db, eng):
    """已 cancelled 任务不被 worker 认领：_process 返回 'cancelled'，不 mark_started、
    不进 token 获取，DB 终态保持 cancelled（不落不一致）。"""
    await _create(tmp_db, "t-abandon", status="pending")
    await cancel_task("t-abandon")  # 模拟 cancel 端点先落终态
    outcome = await eng._process("t-abandon")
    assert outcome == "cancelled"
    row = await tmp_db.get("t-abandon")
    assert row["status"] == "cancelled"
    assert row["started_at"] is None  # 未被 mark_started（不占用 worker 槽位语义）


# ── 阶段进度事件（append-only 埋点）──────────────────────────


@pytest.mark.asyncio
async def test_progress_event_queued_stage(tmp_db, eng):
    """入队阶段 pub：status_detail=queued / progress=5。"""
    new_id = await eng.submit_priority("hello", "1:1", False, "default", priority=2)
    await asyncio.sleep(0.05)  # 让 ensure_future 的 publish 落地
    events = hub.get_task_events(new_id)
    pending_ev = [e for e in events if e["data"].get("status") == "pending"]
    assert pending_ev, "应发布 pending status 事件"
    assert pending_ev[0]["data"]["status_detail"] == "queued"
    assert pending_ev[0]["data"]["progress"] == 5
    # 旧字段保留（向后兼容）
    assert "queue_pos" in pending_ev[0]["data"]


@pytest.mark.asyncio
async def test_cancel_publishes_terminal_event(tmp_db, eng):
    """取消终态 pub：per-task result 事件带 status_detail=cancelled / progress=100。"""
    await _create(tmp_db, "t-cancel-ev")
    await cancel_task("t-cancel-ev")
    await asyncio.sleep(0.05)  # broadcast 内部 publish 异步落地
    events = hub.get_task_events("t-cancel-ev")
    result_ev = [e for e in events if e["event"] == "result"]
    assert result_ev, "应发布 result 终态事件"
    last = result_ev[-1]["data"]
    assert last["status"] == "cancelled"
    assert last["status_detail"] == "cancelled"
    assert last["progress"] == 100


@pytest.mark.asyncio
async def test_retry_completed_source_400(tmp_db, eng):
    """L4（审查）：已完成/处理中/归档源任务不可重试 → 400（防复制运行中/已完成任务）。"""
    from api.errors import AppError
    from api.routes.tasks import retry_task

    await _create(tmp_db, "t-completed-src", status="completed")
    with pytest.raises(AppError) as ei:
        await retry_task(_make_request(), "t-completed-src")
    assert ei.value.status_code == 400
