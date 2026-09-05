"""写操作类端点（P0-7 拆分自 admin.py）。

携带 check_admin_key 鉴权的管理写操作：DLQ 重试 / DLQ 清空。
v7.7 鉴权契约定稿：封禁/解封/DLQ 清空/重试/日志 WS/priority=0 队列仅管理员可操作。
"""

from __future__ import annotations

from fastapi import Query, Request

from ...audit import audit_log
from ...auth import check_admin_key
from ...config import config
from ...errors import AppError, ErrorCodes
from ...meta import db
from ._common import router  # noqa: F401  (共享 router 单例，来自 _common)


@router.get("/v1/dead-letter-queue")
async def dead_letter_queue(limit: int = Query(20, ge=1, le=100)):
    """死信队列。"""
    items = await db.list_dlq(limit)
    return {"items": items, "count": len(items)}


@router.post("/v1/dead-letter-queue/{task_id}/retry")
async def retry_dlq_task(task_id: str, request: Request):
    """死信队列重试（v6.7.0：补管理 Key 鉴权，写操作须携带 IF_ADMIN_KEYS 管理 Key）。"""
    check_admin_key(request, scope="admin-dlq")
    client_ip = request.client.host if request.client else "unknown"
    audit_log.record("dlq.retry", client_ip, f"task:{task_id}", "重试死信队列任务")
    if config.IF_DLQ_REQUEUE:
        from ...worker import engine as _engine  # noqa: PLC0415

        requeued = await _engine.requeue_dlq_task(task_id)
        if not requeued:
            raise AppError(ErrorCodes.BAD_REQUEST, f"任务 {task_id} 重入队失败（不存在或队列已满）", 409)
        await db.retry_dlq(task_id)
        return {"status": "ok", "detail": f"任务 {task_id} 已重新入队（pending，等待 worker 处理）"}
    await db.retry_dlq(task_id)
    return {"status": "ok", "detail": f"任务 {task_id} 已从死信队列移除"}


@router.delete("/v1/dead-letter-queue")
async def clear_dlq(request: Request):
    """清空死信队列所有记录（v6.7.0：补管理 Key 鉴权，写操作须携带 IF_ADMIN_KEYS 管理 Key）。"""
    check_admin_key(request, scope="admin-dlq")
    client_ip = request.client.host if request.client else "unknown"
    audit_log.record("dlq.clear", client_ip, "dlq", "清空死信队列")
    await db.clear_dlq()
    return {"status": "ok", "detail": "死信队列已清空"}
