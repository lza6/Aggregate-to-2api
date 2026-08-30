"""PoolSettings 子配置。"""

from __future__ import annotations

from pydantic import BaseModel


class PoolSettings(BaseModel):
    """Token 池配置组。"""

    token_pool_size: int = 6
    token_double_buffer_size: int = 12
    token_ttl: int = 90
    token_wait_timeout: int = 30
