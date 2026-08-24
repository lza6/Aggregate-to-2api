"""任务查询 / 全局 SSE 广播 / 黑匣子打开（v4.2 拆分：main.py 迁移）。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ..meta import db
from ..db import task_to_public
from ..errors import AppError, ErrorCodes
from ..dispatch import sse_task_events, broadcast_task_event
from ..models import TaskInfo
from ..sse_events import hub, task_events_generator, publish_task_event

router = APIRouter()


@router.get("/v1/tasks")
async def list_tasks(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, description="筛选：pending/processing/completed/error"),
    model: str | None = Query(None, description="筛选：模型 id，如 imagefree/default"),
    sort: str = Query("created_at", description="排序字段：created_at/duration_sec"),
):
    """任务列表，按创建时间降序，支持分页和筛选。"""
    items, total = await db.list_tasks(
        limit=limit, offset=offset,
        status=status, model=model,
        sort=sort,
    )
    return {
        "items": [task_to_public(t) for t in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/v1/tasks/{task_id}", response_model=TaskInfo)
async def get_task(task_id: str):
    task = await db.get(task_id)  # 用 get 而非 get_public，返回完整字段含 prompt
    if not task:
        raise AppError(ErrorCodes.NOT_FOUND, "task 不存在", 404)
    return TaskInfo(**task_to_public(task))


# ── 全局 SSE 任务广播（向后兼容 /v1/events/tasks）──
@router.get("/v1/events/tasks", include_in_schema=False)
async def sse_task_events_route():
    return await sse_task_events()


# ── v4.2: 每任务 SSE 事件流（黑匣子打开）──
@router.get("/v1/tasks/{task_id}/events", include_in_schema=False)
async def task_events_endpoint(task_id: str, request: Request):
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