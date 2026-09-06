"""HTTPSettings 子配置。"""

from __future__ import annotations

from typing import Any

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

    @classmethod
    def from_settings(cls, s: Any) -> HTTPSettings:
        """从 Settings 实例提取字段构造 HTTPSettings。"""
        return cls(
            host=s.host,
            port=s.port,
            proxy=s.proxy,
            user_agent=s.user_agent,
            max_connections=s.if_http_max_connections,
            keepalive=s.if_http_keepalive,
            upstream_max_inflight=s.if_upstream_max_inflight,
        )
