"""Agent 路由（P1-A）：/v1/agent/* 端点。

新增端点（向后兼容，不破坏现有 /v1/generate /v1/chat/completions）：
- GET  /v1/agent/skills          列出可用 skills（按 scene 分组）
- POST /v1/agent/intent          意图分类（规则正则 + LLM）
- GET  /v1/agent/memory          查询用户记忆（mem_persona）
- POST /v1/agent/memory/observe  L0 观察写入
- GET  /v1/agent/health          agent 子系统健康

鉴权：复用 auth.guard_chat_request（与 chat 端点同 Key）。
开关：IF_AGENT_SKILLS_ENABLED=0 关闭 skills 列表，回退空。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from .. import auth
from ..errors import AppError, ErrorCodes

router = APIRouter()
log = logging.getLogger("imagefree_api.agent")


class IntentRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)


class ObserveRequest(BaseModel):
    user_key: str = Field("default", max_length=128)
    scene: str = Field(..., max_length=64)
    content: str = Field(..., max_length=8000)
    importance: float = Field(0.5, ge=0.0, le=1.0)


@router.get("/v1/agent/skills")
async def list_skills(request: Request):
    """列出可用 skills（按 scene 分组）。"""
    auth.guard_chat_request(request)
    from ..skills import skill_index

    records = skill_index.all()
    by_scene: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        by_scene.setdefault(rec.scene, []).append(
            {
                "name": rec.name,
                "description": rec.description,
                "scene": rec.scene,
            }
        )
    return {"items": by_scene, "count": len(records)}


@router.post("/v1/agent/intent")
async def classify_intent_endpoint(payload: IntentRequest, request: Request):
    """意图分类：规则正则兜底 + LLM 二次分类。"""
    auth.guard_chat_request(request)
    from .intent import classify_intent

    result = await classify_intent(payload.prompt)
    return {
        "scene": result.scene,
        "provider_hint": result.provider_hint,
        "skill_hint": result.skill_hint,
        "confidence": round(result.confidence, 4),
        "matched_rule": result.matched_rule,
        "llm_used": result.llm_used,
    }


@router.get("/v1/agent/memory")
async def query_memory(
    request: Request,
    scene: str = Query("image", max_length=64),
    layer: str = Query("L1", max_length=8),
    limit: int = Query(10, ge=1, le=100),
    user_key: str = Query("default", max_length=128),
):
    """查询用户记忆（供 chat 端点注入上下文）。"""
    auth.guard_chat_request(request)
    from .memory import MEMORY_CONSOLIDATION_ENABLED, memory_store

    if not MEMORY_CONSOLIDATION_ENABLED:
        return {"items": [], "count": 0, "enabled": False}
    records = await memory_store.query(user_key, scene, layer=layer, limit=limit)
    return {
        "items": [
            {
                "id": r.id,
                "layer": r.layer,
                "scene": r.scene,
                "content": r.content,
                "importance": r.importance,
                "created_at": r.created_at,
            }
            for r in records
        ],
        "count": len(records),
        "enabled": True,
    }


@router.post("/v1/agent/memory/observe")
async def observe_memory(payload: ObserveRequest, request: Request):
    """L0 观察写入（chat/生成请求的事实片段）。"""
    auth.guard_chat_request(request)
    from .memory import MEMORY_CONSOLIDATION_ENABLED, memory_store

    if not MEMORY_CONSOLIDATION_ENABLED:
        raise AppError(ErrorCodes.FORBIDDEN, "记忆子系统未启用", 403)
    record_id = await memory_store.observe(payload.user_key, payload.scene, payload.content, payload.importance)
    return {"id": record_id, "stored": True}


@router.get("/v1/agent/health")
async def agent_health(request: Request):
    """agent 子系统健康快照。"""
    auth.guard_chat_request(request)
    from .guard import PROVIDER_RISK_TIER_ENABLED
    from .intent import INTENT_CLASSIFIER_ENABLED
    from .memory import MEMORY_CONSOLIDATION_ENABLED

    return {
        "intent_classifier": INTENT_CLASSIFIER_ENABLED,
        "memory_consolidation": MEMORY_CONSOLIDATION_ENABLED,
        "provider_risk_tier": PROVIDER_RISK_TIER_ENABLED,
        "memory_tables": {
            "L0": "mem_observations",
            "L1": "mem_atoms",
            "L2": "mem_scenarios",
            "L3": "mem_persona",
        },
    }


__all__ = ["router"]
