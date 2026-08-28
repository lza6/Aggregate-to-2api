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
from ..request_guard import check_generate_request

router = APIRouter()


def _guard(request: Request, prompt: str) -> None:
    """入口防护：per-IP 限速 + API Key 鉴权（全站写操作统一要求）。

    生图/图生图端点现在与聊天端点一致，必须携带有效 API Key
    （Authorization: Bearer / X-API-Key / ?api_key=）。未配置 IF_API_KEYS 时保持开放兼容。
    """
    from .. import auth
    auth.guard_generate_request(request)
    check_generate_request(request, prompt)


def _prepare(request: Request, req: GenerateRequest) -> None:
    """同步/异步共用的提交前置：鉴权限流 → 模型/比例校验 → 调用方真实 IP与客户端标识回填。

    v4.2 P3-1: sync 与 async 唯一差别只在“是否等待”，提交前必须走完全同一路径，
    确保鉴权/校验/IP 取证三者语义一致，不各自实现。
    """
    _guard(request, req.prompt)
    _validate_ratio(req.aspect_ratio)
    _validate_model(req.model, "txt2vid" if req.duration else "txt2img")
    req.client_ip = request.state.client_ip if hasattr(request.state, "client_ip") else None
    req.user_agent = request.headers.get("user-agent", "")[:500] if request.headers.get("user-agent") else "Unknown"


async def _submit(req: GenerateRequest) -> str:
    """统一提交入口：入队/幂等命中均返回 task_id，同步轮询与异步直接返回共用。"""
    try:
        return await _dispatch_generate(req)
    except QueueFull as e:
        raise AppError(ErrorCodes.QUEUE_FULL, str(e), 429)


@router.post("/v1/generate", response_model=TaskInfo, summary="生成图片/视频（同步等待）")
async def generate_sync(request: Request, req: GenerateRequest):
    _prepare(request, req)
    task_id = await _submit(req)
    # 短轮询等待：客户端断开只取消等待协程，生成任务仍由引擎继续（与 async 语义一致）
    task = await engine.wait_result(task_id, config.SYNC_TIMEOUT)
    if task["status"] in ("completed", "error"):
        return TaskInfo(**task_to_public(task))
    body = task_to_public(task)
    body["status"] = "queued"
    body["error"] = "仍在排队/生成中，GET /v1/tasks/{id} 查询"
    return JSONResponse(status_code=202, content=body,
                        headers={"Location": f"{request.base_url}v1/tasks/{task_id}"})


@router.post("/v1/generate/async", response_model=TaskInfo, summary="生成图片/视频（异步，立即返回）")
async def generate_async(request: Request, req: GenerateRequest):
    _prepare(request, req)
    task_id = await _submit(req)
    headers = {"Location": f"/v1/tasks/{task_id}"}
    return TaskInfo(**task_to_public(await db.get_public(task_id)))


@router.post("/v1/edit", response_model=TaskInfo, summary="图生图（AI 照片编辑，异步提交）")
async def edit_image_route(request: Request, req: EditRequest):
    _guard(request, req.prompt or "")
    return await edit_image(req)


@router.get("/v1/edit/tasks/{job_id}", response_model=TaskInfo)
async def get_edit_task(job_id: str):
    task = await db.get_public(job_id)
    if not task:
        raise AppError(ErrorCodes.NOT_FOUND, "图生图任务不存在", 404)
    return TaskInfo(**task_to_public(task))