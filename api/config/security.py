"""SecuritySettings 子配置。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SecuritySettings(BaseModel):
    """安全 / 鉴权配置组。"""

    gallery_password: str = ""
    cors_origins: str = Field("*", validation_alias="IF_CORS_ORIGINS")
    # v4.4: 全局 API Key 保护（防滥用）。逗号分隔多个 Key；空列表 = 开放。
    api_keys: list[str] = Field(default_factory=list, validation_alias="IF_API_KEYS")
    # v4.4: 聊天端点每分钟限流（0 = 不限）
    chat_requests_per_minute: int = Field(60, validation_alias="IF_CHAT_RATE_LIMIT")
    # v4.4: 聊天端点每分钟限流（0 = 不限）
    chat_requests_per_minute: int = Field(60, validation_alias="IF_CHAT_RATE_LIMIT")