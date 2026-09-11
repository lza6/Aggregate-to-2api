"""api/routes/agent_human.py — v12.0.1 T3 human_input 审批端点。

- GET  /v1/agent/human-inbox                      审批请求列表（run_id/status 过滤）
- POST /v1/agent/human-inbox/{req_id}/decision    审批决策（approve/reject + note）

鉴权：复用 auth.guard_chat_request（公益开放 + per-IP 限流；生产建议改管理 Key，
与 admin 面板同保护级别——审批是写操作）。
开关：human_input 节点侧由 IF_HUMAN_INPUT_ENABLED 控制；本端点始终可用
（便于审批方先行集成），未知 req_id → 404。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
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
    """审批决策（幂等：仅 pending 可决策，重复决策返回现状）。"""
    auth.guard_chat_request(request)
    from ..agent.human_inbox import human_inbox

    req = human_inbox.decide(req_id, payload.decision, payload.note)
    if req is None:
        raise AppError(ErrorCodes.NOT_FOUND, f"审批请求不存在：{req_id}", 404)
    log.info("human_inbox 决策 req=%s decision=%s note=%s", req_id, payload.decision, payload.note[:100])
    return human_inbox.public_state(req)


__all__ = ["router"]
