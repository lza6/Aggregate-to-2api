"""生成相关路由（v4.2 拆分：main.py 迁移）。"""
from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import config
from ..models import GenerateRequest, EditRequest, TaskInfo, TaskInfo  # noqa: F401
from ..meta import db, engine, registry, _DOCS_PAGE
from ..solver_guard import solver_guard
from ..sse_events import publish_task_event
from ..dispatch import _dispatch_generate
from ..dispatch_edit import _dispatch_edit, _dispatch_edit_multi, edit_image
from ..dispatch import _validate_ratio, _validate_model
from ..dispatch import _parse_input_image, _parse_input_images
from ..dispatch import QueueFull
from ..db import task_to_public
from ..errors import AppError, ErrorCodes
from .. import imagefree_client

router = APIRouter()


@router.post("/v1/generate", response_model=TaskInfo, summary="生成图片/视频（同步等待）")
async def generate_sync(request: Request, req: GenerateRequest):
    _validate_ratio(req.aspect_ratio)
    _validate_model(req.model, "txt2vid" if req.duration else "txt2img")
    try:
        task_id = await _dispatch_generate(req)
    except QueueFull as e:
        raise AppError(ErrorCodes.QUEUE_FULL, str(e), 429)
    task = await engine.wait_result(task_id, config.SYNC_TIMEOUT)
    if task["status"] in ("completed", "error"):
        return TaskInfo(**task_to_public(task))
    body = task_to_public(task)
    body["status"] = "queued"
    body["error"] = "仍在排队/生成中，GET /v1/tasks/{id} 查询"
    return JSONResponse(status_code=202, content=body,
                        headers={"Location": f"{request.base_url}v1/tasks/{task_id}"})


@router.post("/v1/generate/async", response_model=TaskInfo, summary="生成图片/视频（异步，立即返回）")
async def generate_async(req: GenerateRequest):
    _validate_ratio(req.aspect_ratio)
    _validate_model(req.model, "txt2vid" if req.duration else "txt2img")
    try:
        task_id = await _dispatch_generate(req)
    except QueueFull as e:
        raise AppError(ErrorCodes.QUEUE_FULL, str(e), 429)
    headers = {"Location": f"/v1/tasks/{task_id}"}
    return TaskInfo(**task_to_public(await db.get_public(task_id)))


@router.post("/v1/edit", response_model=TaskInfo, summary="图生图（AI 照片编辑，异步提交）")
async def edit_image_route(req: EditRequest):
    return await edit_image(req)


@router.get("/v1/edit/tasks/{job_id}", response_model=TaskInfo)
async def get_edit_task(job_id: str):
    task = await db.get_public(job_id)
    if not task:
        raise AppError(ErrorCodes.NOT_FOUND, "图生图任务不存在", 404)
    return TaskInfo(**task_to_public(task))