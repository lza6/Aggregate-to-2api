"""API 共享模型（v4.2 拆分：main.py 迁移）。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from . import config


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=config.MAX_PROMPT_LEN)
    aspect_ratio: str = Field("1:1", pattern=r"^\d+:\d+$")
    download: bool = Field(False, description="是否同时下载图片并返回 base64")
    model: str = Field(
        "imagefree/default",
        description="模型 id，见 GET /v1/models（格式：<提供商>/<真实模型名>，如 nanobanana/nano-banana-pro）",
    )
    resolution: str = Field("1K", description="分辨率：1K/2K/4K 或视频 480p/720p")
    duration: int | None = Field(None, ge=4, le=15, description="视频时长秒数：4/8/12/15")
    images: list[str] = Field(
        [], description="图生视频输入图（data URI 数组），img2vid 能力的 provider 使用"
    )
    priority: int | None = Field(None, ge=0, le=2, description="优先级：0=admin, 1=paid, 2=normal；不传默认 normal")
    idempotency_key: str | None = Field(
        None,
        max_length=128,
        description="幂等 key：同一 key 重复提交返回相同 task_id（IF_IDEMPOTENCY_ENABLED=1 时生效）",
    )
    # v4.4.3: 调用方真实 IP（服务端从 X-Forwarded-For / socket 自动填充，客户端无需传）
    client_ip: str | None = Field(None, max_length=64, description="调用方 IP（服务端自动回填，客户端无需传）")
    user_agent: str | None = Field(None, max_length=512, description="客户端程序标识（User-Agent，服务端自动回填）")


class EditRequest(BaseModel):
    """图生图（AI 照片编辑）：输入一张图（或最多 3 张参考图）+ 提示词 → 生成变体。"""

    image: str = Field(
        "", description="输入图（单张，向后兼容）：data URI（image/png 等;base64）或公开 http(s) 图片 URL"
    )
    images: list[str] = Field(
        [], description="输入图数组（最多 3 张）：data URI 数组，每项格式 data:image/*;base64,..."
    )
    prompt: str = Field(
        ..., min_length=1, max_length=config.MAX_PROMPT_LEN, description="编辑指令，例如：make it a watercolor painting"
    )
    download: bool = Field(False, description="完成后是否同时下载结果图并返回 base64")
    model: str = Field("imagefree/default", description="模型 id，见 GET /v1/models（图生图能力模型）")


class TaskInfo(BaseModel):
    id: str
    status: str
    image_url: str | None = None
    image_base64: str | None = None
    image_mime: str | None = None
    error: str | None = None
    created_at: float | None = None
    duration_sec: float | None = None
    type: str = "txt"
    model: str = "default"
    prompt: str | None = None
    aspect_ratio: str | None = None
    client_ip: str | None = None
    client_location: str | None = None
    user_agent: str | None = None
    timings: dict | None = None
