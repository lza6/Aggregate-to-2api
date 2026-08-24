"""SolverSettings 子配置。"""
from __future__ import annotations

from pydantic import BaseModel


class SolverSettings(BaseModel):
    """CF solver / Turnstile 求解配置组。"""

    base_url: str = "https://imagefree.net"
    sitekey: str = "0x4AAAAAACE-XLGoQUckKKm_"
    cf_solver_url: str = "http://127.0.0.1:8001"
    turnstile_timeout: int = 90
    turnstile_poll_interval: float = 2.0
    solve_circuit_threshold: int = 5
    solve_circuit_probe_seconds: int = 30
    solve_stats_window_seconds: int = 300
    healthz_cache_ttl: int = 5
    token_prefetch_concurrency: int = 1
    prefetch_after_solve_delay: float = 0.0
    prefetch_ema_alpha: float = 0.3