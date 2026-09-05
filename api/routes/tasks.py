"""任务查询 / 全局 SSE 广播 / 黑匣子打开（v4.2 拆分：main.py 迁移）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request, WebSocket
from fastapi.responses import StreamingResponse

from ..db import task_to_public
from ..dispatch import sse_task_events
from ..errors import AppError, ErrorCodes
from ..meta import db
from ..models import TaskInfo
from ..sse_events import task_events_generator

router = APIRouter()


@router.get("/v1/tasks")
async def list_tasks(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, description="筛选：pending/processing/completed/error"),
    model: str | None = Query(None, description="筛选：模型 id，如 imagefree/default"),
    sort: str = Query("created_at", description="排序字段：created_at/duration_sec"),
) -> dict[str, Any]:
    """任务列表，按创建时间降序，支持分页和筛选。"""
    items, total = await db.list_tasks(
        limit=limit,
        offset=offset,
        status=status,
        model=model,
        sort=sort,
    )
    return {
        "items": [task_to_public(t) for t in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/v1/tasks/{task_id}", response_model=TaskInfo)
async def get_task(task_id: str) -> TaskInfo:
    task = await db.get(task_id)  # 用 get 而非 get_public，返回完整字段含 prompt
    if not task:
        raise AppError(ErrorCodes.NOT_FOUND, "task 不存在", 404)
    return TaskInfo(**task_to_public(task))


@router.get("/v1/tasks/{task_id}/logs", include_in_schema=False)
async def task_logs(task_id: str, lines: int = Query(200, ge=5, le=2000)) -> dict[str, Any]:
    """任务 ID → 全链路日志串联（Section 16 可观测性 / P3）。

    把与某任务关联的日志（log_buffer 内存缓冲，按 task_id 过滤）+ 慢日志画像 +
    SSE 已发布事件 聚合到一处，供排障时「一个任务 ID 看全链路」。

    - logs：log_buffer 中 message 含该 task_id 的条目（由 engine/dispatch 记录）；
    - slow：slow_log 中该 task 的画像样本（若有）；
    - events：该任务已发布的 SSE 事件（hub 回放）；
    - task：DB 中的任务终态（若有）。
    """
    import uuid as _uuid

    from ..log_buffer import log_buffer as _lb
    from ..slow_log import slow_log as _slow
    from ..sse_events import hub as _hub

    # 0. task_id 必须为完整 uuid4（防任意子串误伤其他任务日志）
    try:
        _uuid.UUID(task_id)
    except (ValueError, AttributeError, TypeError):
        raise AppError(ErrorCodes.BAD_REQUEST, "task_id 需为完整 UUID", 422)

    # 1. 日志过滤（B2: 优先 trace_id 精确串联，无则回退 task_id 子串匹配）
    _task_row_preview = await db.get(task_id)
    trace_id_hint = ""
    if _task_row_preview:
        trace_id_hint = _task_row_preview.get("trace_id") or ""
    if trace_id_hint:
        log_entries = [e for e in _lb.snapshot(lines) if e.get("trace_id") == trace_id_hint][-lines:]
    else:
        log_entries = [e for e in _lb.snapshot(lines) if task_id in (e.get("message") or "")][-lines:]

    # 2. 慢日志画像
    slow_entries = [s for s in _slow.snapshot() if s.task_id == task_id]

    # 3. SSE 事件回放
    try:
        events = list(_hub.get_task_events(task_id))
    except Exception:
        events = []

    # 4. DB 任务终态（已在上方预取为 _task_row_preview）
    task_row = _task_row_preview
    trace_id = trace_id_hint or task_id

    return {
        "task_id": task_id,
        "trace_id": trace_id,
        "task": task_row,
        "logs": log_entries,
        "slow": [
            {
                "model": s.model,
                "provider": s.provider,
                "queue_ms": round(s.queue_ms, 1),
                "wait_token_ms": round(s.wait_token_ms, 1),
                "solve_ms": round(s.solve_ms, 1),
                "upstream_ms": round(s.upstream_ms, 1),
                "retry_ms": round(s.retry_ms, 1),
                "total_ms": round(s.total_ms, 1),
                "slowest_stage": s.slowest_stage(),
                "status": s.status,
                "trace_id": getattr(s, "trace_id", "") or trace_id,
                "submit_ms": round(getattr(s, "submit_ms", 0.0), 1),
                "poll_ms": round(getattr(s, "poll_ms", 0.0), 1),
            }
            for s in slow_entries
        ],
        "events": events,
        "count": {"logs": len(log_entries), "slow": len(slow_entries), "events": len(events)},
    }


# ── 全局 SSE 任务广播（向后兼容 /v1/events/tasks）──
@router.get("/v1/events/tasks", include_in_schema=False)
async def sse_task_events_route() -> StreamingResponse:
    return await sse_task_events()  # type: ignore[no-any-return,no-untyped-call]


# ── v4.2: 每任务 SSE 事件流（黑匣子打开）──
@router.get("/v1/tasks/{task_id}/events", include_in_schema=False)
async def task_events_endpoint(task_id: str, request: Request) -> StreamingResponse:
    """每任务 SSE 事件流：status/progress/result/error + 心跳 + Last-Event-ID 断线补偿。

    - 连接后先回放该任务已产生的全部事件（Last-Event-ID 头 → 只回放 id 之后的）
    - 再实时推送后续事件；15s 心跳保活
    - result/error 终态后自动断开
    """
    return StreamingResponse(
        task_events_generator(task_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── v8.0 P1-6: 每任务 WebSocket 双向事件通道（与 SSE 并存）──
@router.websocket("/v1/tasks/{task_id}/ws")
async def task_ws_events_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket 双向任务事件流：客户端可发 cancel/query，服务端推送事件 + 心跳 sequence。

    - 连接后回放历史事件 + 实时推送
    - 客户端发 {"action":"cancel"} 取消 / {"action":"query"} 查询状态
    - 心跳带 sequence number（客户端检测丢包）
    - result/error 终态后自动断开
    """
    from ..ws_events import ws_task_events

    await ws_task_events(websocket, task_id)

