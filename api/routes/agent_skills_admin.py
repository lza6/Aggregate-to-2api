"""技能沉淀管理路由（指南 B2 / P0-1 手动收藏 MVP）。

端点：
- POST   /v1/agent/skills/save-from-run  保存 DAG run 为技能草稿（公开；IF_SKILL_SEDIMENT_ENABLED 开关）
- GET    /v1/agent/skills/manage         管理列表（admin；含草稿/已批/已拒）
- GET    /v1/agent/skills/mine           我的已批准技能（公开只读）
- POST   /v1/agent/skills/{id}/approve   审批通过（admin）
- POST   /v1/agent/skills/{id}/reject    拒绝（admin）
- DELETE /v1/agent/skills/{id}           删除（admin）

安全：保存前强制过 skill_scan 静态扫描（B1b 闸门），risk_score >= IF_SKILL_SCAN_REJECT 拒绝入库。
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import auth
from ..agent import skill_sediment as _sed
from ..agent.skill_scan import scan_skill
from ..agent.skill_sediment import VALID_STATUSES

router = APIRouter()
log = logging.getLogger("agent.skills_admin")


def _sediment_enabled() -> bool:
    from ..config import get_settings

    return bool(get_settings().if_skill_sediment_enabled)


class SaveFromRunRequest(BaseModel):
    run_id: str = Field("", max_length=128)
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field("", max_length=300)
    prompt_template: str = Field(..., min_length=1, max_length=8000)
    params: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field("", max_length=500)


class StatusRequest(BaseModel):
    pass


@router.post("/v1/agent/skills/save-from-run")
async def save_from_run(body: SaveFromRunRequest, request: Request):
    """把 DAG run 保存为技能草稿（先扫描后入库）。"""
    if not _sediment_enabled():
        raise HTTPException(status_code=404, detail="技能沉淀未启用（IF_SKILL_SEDIMENT_ENABLED=1 开启）")
    auth.guard_chat_request(request)

    scan = scan_skill(f"{body.name}\n{body.description}\n{body.prompt_template}\n{body.notes}")
    if scan.rejected:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "技能内容未通过安全扫描，已拒绝入库",
                "risk_score": scan.risk_score,
                "threshold": scan.threshold,
                "findings": scan.findings,
            },
        )

    existing = await _sed.skill_sediment_store.get_by_name(body.name.strip())
    if existing:
        raise HTTPException(status_code=409, detail=f"技能名已存在: {body.name.strip()}")

    try:
        row = await _sed.skill_sediment_store.save_draft(
            name=body.name,
            description=body.description,
            prompt_template=body.prompt_template,
            params=body.params,
            source_run_id=body.run_id or None,
            risk_score=scan.risk_score,
            scan_findings=scan.findings,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "skill": row}


@router.get("/v1/admin/skills")
async def manage_skills(request: Request, status: str | None = None):
    """管理列表（admin）：全部状态；可过滤 status。"""
    auth.check_admin_key(request, scope="admin-skills")
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"非法状态: {status}")
    items = await _sed.skill_sediment_store.list_skills(status=status)
    return {"ok": True, "count": len(items), "items": items}


@router.get("/v1/agent/my-skills")
async def my_approved_skills(request: Request):
    """我的已批准技能（公开只读，供前端展示/复用）。"""
    auth.guard_chat_request(request)
    items = await _sed.skill_sediment_store.list_skills(status="approved")
    return {"ok": True, "count": len(items), "items": items}


@router.post("/v1/admin/skills/{skill_id}/approve")
async def approve_skill(skill_id: str, request: Request):
    """审批通过（admin）：草稿/已拒 → approved。"""
    auth.check_admin_key(request, scope="admin-skills")
    ok = await _sed.skill_sediment_store.set_status(skill_id, "approved")
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"ok": True, "status": "approved", "id": skill_id}


@router.post("/v1/admin/skills/{skill_id}/reject")
async def reject_skill(skill_id: str, request: Request):
    """拒绝（admin）。"""
    auth.check_admin_key(request, scope="admin-skills")
    ok = await _sed.skill_sediment_store.set_status(skill_id, "rejected")
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"ok": True, "status": "rejected", "id": skill_id}


@router.delete("/v1/admin/skills/{skill_id}")
async def delete_skill(skill_id: str, request: Request):
    """删除技能（admin）。"""
    auth.check_admin_key(request, scope="admin-skills")
    ok = await _sed.skill_sediment_store.delete_skill(skill_id)
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"ok": True, "deleted": skill_id}
