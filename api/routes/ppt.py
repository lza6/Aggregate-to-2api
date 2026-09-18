"""PPT 可编辑产物生成端点（指南 v18 P1-2）。

POST /v1/skills/ppt/generate
  body: {title, subtitle?, pages:[{headline, points[], notes?}], assumptions?}
  200 → application/vnd.openxmlformats-officedocument.presentationml.presentation（PPTX bytes）
开关：IF_PPT_GENERATE=0（缺省）→ 404。依赖 python-pptx（requirements.txt 已声明）。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import auth
from ..skills.ppt.generate_pptx import generate_pptx

router = APIRouter()
log = logging.getLogger("ppt")


class PptOutline(BaseModel):
    title: str = Field("", max_length=120)
    subtitle: str = Field("", max_length=200)
    pages: list[dict] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


def _enabled() -> bool:
    from ..config import get_settings

    return bool(get_settings().if_ppt_generate)


@router.post("/v1/skills/ppt/generate")
async def generate_ppt(body: PptOutline, request: Request):
    """大纲 → PPTX 文件下载。"""
    if not _enabled():
        raise HTTPException(status_code=404, detail="PPT 生成未启用（IF_PPT_GENERATE=1 开启）")
    auth.guard_chat_request(request)
    data = body.model_dump()
    if not body.title or not body.pages:
        raise HTTPException(status_code=422, detail="需提供 title 与至少一页 pages")
    try:
        content = generate_pptx(data)
    except Exception as exc:  # noqa: BLE001
        log.warning("PPT 生成失败: %s", exc)
        raise HTTPException(status_code=500, detail="PPT 生成失败，请检查大纲结构") from exc
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": 'attachment; filename="outline.pptx"', "X-Slides": str(len(body.pages) + 1)},
    )
