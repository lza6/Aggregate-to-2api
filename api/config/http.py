"""HTTPSettings 子配置。"""

from __future__ import annotations

from pydantic import BaseModel


class HTTPSettings(BaseModel):
    """HTTP 连接配置组。"""

    host: str = "127.0.0.1"
    port: int = 8100
    proxy: str | None = None
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    )
    max_connections: int = 100
    keepalive: int = 20
    upstream_max_inflight: int = 30
