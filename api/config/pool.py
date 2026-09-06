"""PoolSettings 子配置。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PoolSettings(BaseModel):
    """Token 池配置组。"""

    token_pool_size: int = 6
    token_double_buffer_size: int = 12
    token_ttl: int = 90
    token_wait_timeout: int = 30

    @classmethod
    def from_settings(cls, s: Any) -> PoolSettings:
        """从 Settings 实例提取字段构造 PoolSettings。"""
        return cls(
            token_pool_size=s.token_pool_size,
            token_ttl=s.token_ttl,
            token_wait_timeout=s.token_wait_timeout,
        )
