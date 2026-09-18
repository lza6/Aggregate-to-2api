"""视频生成任务端点（指南 v18 P1-1，Mock 全链路）。

- POST /v1/video   {prompt, mode: txt2vid|img2vid, duration?, ratio?, image_url?} → {task_id, status: queued}
- GET  /v1/video/{task_id} → {status, progress, url?, error?}
开关：IF_VIDEO_ENABLED=0（缺省）→ 404。Mock provider 秒级完成，零真实付费。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import auth
from ..providers.video_provider import get_video_provider

router = APIRouter()
log = logging.getLogger("video")


class VideoRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    mode: str = Field("txt2vid", pattern="^(txt2vid|img2vid)$")
    duration_seconds: float = Field(5.0, ge=1.0, le=60.0)
    ratio: str = Field("16:9", max_length=16)
    image_url: str = Field("", max_length=500)


def _enabled() -> bool:
    from ..config import get_settings

    return bool(get_settings().if_video_enabled)


@router.post("/v1/video", include_in_schema=True, summary="提交视频生成（Mock）")
async def submit_video(body: VideoRequest, request: Request):
    """提交视频生成任务（Mock 全链路），返回 task_id 供轮询。"""
    if not _enabled():
        raise HTTPException(status_code=404, detail="视频生成未启用（IF_VIDEO_ENABLED=1 开启）")
    auth.guard_chat_request(request)
    provider = get_video_provider()
    task_id = provider.submit(
        prompt=body.prompt,
        mode=body.mode,
        duration_seconds=body.duration_seconds,
        ratio=body.ratio,
    )
    return {"task_id": task_id, "status": "queued", "mode": body.mode}


@router.get("/v1/video/{task_id}", include_in_schema=True, summary="轮询视频任务状态")
async def video_status(task_id: str, request: Request):
    """轮询任务状态：queued/rendering/completed（progress 0-100；完成后含 mock URL）。"""
    if not _enabled():
        raise HTTPException(status_code=404, detail="视频生成未启用（IF_VIDEO_ENABLED=1 开启）")
    auth.guard_chat_request(request)
    provider = get_video_provider()
    job = provider.poll(task_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"视频任务不存在: {task_id}")
    resp = {k: job[k] for k in ("task_id", "status", "progress")}
    if job.get("url"):
        resp["url"] = job["url"]
    resp["ratio"] = job.get("ratio", "16:9")
    resp["mode"] = job.get("mode", "txt2vid")
    return resp
