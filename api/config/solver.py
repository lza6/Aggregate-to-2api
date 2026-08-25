"""SolverSettings 子配置。"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, field_validator


class SolverSettings(BaseModel):
    """CF solver / Turnstile 求解配置组。"""

    base_url: str = "https://imagefree.net"
    sitekey: str = "0x4AAAAAACE-XLGoQUckKKm_"
    cf_solver_url: str = "http://127.0.0.1:8001"
    cf_solver_urls: list[str] = ["http://127.0.0.1:8001"]
    solver_node_weights: dict[str, int] = {}
    solver_rate_limit_cooldown_seconds: float = 60.0
    turnstile_timeout: int = 90
    turnstile_poll_interval: float = 2.0
    solve_circuit_threshold: int = 5
    solve_circuit_probe_seconds: int = 30
    solve_stats_window_seconds: int = 300
    healthz_cache_ttl: int = 5
    token_prefetch_concurrency: int = 1
    prefetch_after_solve_delay: float = 0.0
    prefetch_ema_alpha: float = 0.3

    @field_validator("cf_solver_urls", mode="before")
    @classmethod
    def _coerce_cf_solver_urls(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            urls = [u.strip() for u in v.split(",") if u.strip()]
            return urls if urls else ["http://127.0.0.1:8001"]
        if isinstance(v, (list, tuple)):
            urls = [str(u).strip() for u in v if str(u).strip()]
            return urls if urls else ["http://127.0.0.1:8001"]
        return ["http://127.0.0.1:8001"]