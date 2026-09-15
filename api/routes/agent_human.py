"""api/routes/agent_human.py — v12.0.1 T3 human_input 审批端点。

- GET  /v1/agent/human-inbox                      审批请求列表（run_id/status 过滤）
- POST /v1/agent/human-inbox/{req_id}/decision    审批决策（approve/reject + note）
- GET  /v1/agent/human-inbox/export               导出全部历史审批（v14 P1，csv/json）
- GET  /v1/agent/human-inbox/history              分页历史（v14 P1，status/limit/offset）

鉴权（v12.x P0-2）：
- 列表 GET：auth.guard_chat_request（公益开放 + per-IP 限流，只读）
- 决策 POST / 导出 / 历史：auth.check_admin_key（写操作或全量数据外发；
  IF_ADMIN_KEYS 管理 Key，未配置默认 403；本地运维开放模式 IF_ADMIN_KEY_OPEN=1
  可放行，与 admin 面板同保护级别）
开关：human_input 节点侧由 IF_HUMAN_INPUT_ENABLED 控制；本端点始终可用
（便于审批方先行集成），未知 req_id → 404。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import auth
from ..errors import AppError, ErrorCodes

router = APIRouter()
log = logging.getLogger("routes.agent_human")


class DecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject)$")
    note: str = Field("", max_length=500)


@router.get("/v1/agent/human-inbox")
async def inbox_list(request: Request, run_id: str = "", status: str = ""):
    """审批请求列表（最近在前）。"""
    auth.guard_chat_request(request)
    from ..agent.human_inbox import human_inbox

    reqs = human_inbox.list(run_id=run_id or None, status=status or None)
    return {"items": [human_inbox.public_state(r) for r in reqs], "count": len(reqs)}


@router.post("/v1/agent/human-inbox/{req_id}/decision")
async def inbox_decide(req_id: str, payload: DecisionRequest, request: Request):
    """审批决策（幂等：仅 pending 可决策，重复决策返回现状）。

    v12.x P0-2：写操作挂管理 Key 校验（IF_ADMIN_KEYS）；未配置默认 403，
    本地运维可用 IF_ADMIN_KEY_OPEN=1 开放。
    """
    auth.check_admin_key(request, scope="admin-human-inbox")
    from ..agent.human_inbox import human_inbox

    req = human_inbox.decide(req_id, payload.decision, payload.note)
    if req is None:
        raise AppError(ErrorCodes.NOT_FOUND, f"审批请求不存在：{req_id}", 404)
    log.info("human_inbox 决策 req=%s decision=%s note=%s", req_id, payload.decision, payload.note[:100])
    return human_inbox.public_state(req)


@router.get("/v1/agent/human-inbox/export")
async def inbox_export(request: Request, format: str = "csv"):
    """导出全部历史审批（v14 P1）。

    csv → text/csv attachment（UTF-8 BOM，Excel 直开）；json → application/json。
    全量数据外发，挂管理 Key（同 decision 端点保护级别）。
    """
    auth.check_admin_key(request, scope="admin-human-inbox")
    from ..agent.human_inbox import human_inbox

    try:
        payload = human_inbox.export(format)
    except ValueError as exc:
        raise AppError(ErrorCodes.BAD_REQUEST, str(exc), 400) from exc
    if format == "json":
        return Response(content=payload, media_type="application/json")
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=human_inbox_export.csv"},
    )


@router.get("/v1/agent/human-inbox/history")
async def inbox_history(
    request: Request,
    status: str = "",
    limit: int = 100,
    offset: int = 0,
):
    """分页审批历史（v14 P1，最近在前；管理 Key 同上）。

    返回 items/count/total：count=本页条数，total=过滤后总数（offset 分页锚点）。
    """
    auth.check_admin_key(request, scope="admin-human-inbox")
    from ..agent.human_inbox import human_inbox

    if limit < 1 or offset < 0:
        raise AppError(ErrorCodes.BAD_REQUEST, "limit 须 >=1，offset 须 >=0", 400)
    reqs = human_inbox.list(status=status or None)
    total = len(reqs)
    page = reqs[offset : offset + limit]
    return {
        "items": [human_inbox.public_state(r) for r in page],
        "count": len(page),
        "total": total,
    }


__all__ = ["router"]
