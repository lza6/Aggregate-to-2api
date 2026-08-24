"""SecuritySettings 子配置。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SecuritySettings(BaseModel):
    """安全 / 鉴权配置组。"""

    gallery_password: str = ""
    cors_origins: str = Field("*", validation_alias="IF_CORS_ORIGINS")