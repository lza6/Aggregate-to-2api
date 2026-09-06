"""SolverSettings 子配置。"""

from __future__ import annotations

import json
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
    # P1-6 IdleTimeout：节点空闲超时标记 idle，select_node 优先非 idle；0=关闭。
    solver_idle_timeout_seconds: float = 0.0
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

    @classmethod
    def from_settings(cls, s: Any) -> SolverSettings:
        """从 Settings 实例提取字段构造 SolverSettings（含 url/weight 规范化）。"""
        # ── Solver URLs 规范化 ──
        resolved_solver_urls: list[str] = []
        if isinstance(s.cf_solver_urls, str):
            resolved_solver_urls = [u.strip() for u in s.cf_solver_urls.split(",") if u.strip()]
        elif isinstance(s.cf_solver_urls, (list, tuple)):
            resolved_solver_urls = [str(u).strip() for u in s.cf_solver_urls if str(u).strip()]

        # 若 CF_SOLVER_URLS 未显式自定义（仅默认值）但指定了单个 CF_SOLVER_URL，则以 CF_SOLVER_URL 为准
        if not resolved_solver_urls or resolved_solver_urls == ["http://127.0.0.1:8001"]:
            if s.cf_solver_url:
                resolved_solver_urls = [s.cf_solver_url]
        elif s.cf_solver_url and s.cf_solver_url not in resolved_solver_urls:
            # 确保主 URL 在列表首位或列表中
            pass
        if not resolved_solver_urls:
            resolved_solver_urls = [s.cf_solver_url or "http://127.0.0.1:8001"]

        # 解析权重（支持 JSON 字符串或 "url1=1,url2=2" 格式）
        resolved_weights: dict[str, int] = {}
        if isinstance(s.solver_node_weights, str) and s.solver_node_weights:
            try:
                resolved_weights = json.loads(s.solver_node_weights)
            except Exception:
                for part in s.solver_node_weights.split(","):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        try:
                            resolved_weights[k.strip()] = int(v.strip())
                        except ValueError:
                            pass
        elif isinstance(s.solver_node_weights, dict):
            resolved_weights = {str(k): int(v) for k, v in s.solver_node_weights.items()}

        return cls(
            base_url=s.base_url,
            sitekey=s.sitekey,
            cf_solver_url=resolved_solver_urls[0] if resolved_solver_urls else s.cf_solver_url,
            cf_solver_urls=resolved_solver_urls,
            solver_node_weights=resolved_weights,
            solver_rate_limit_cooldown_seconds=s.solver_rate_limit_cooldown_seconds,
            solver_idle_timeout_seconds=s.solver_idle_timeout_seconds,
            turnstile_timeout=s.turnstile_timeout,
            turnstile_poll_interval=s.turnstile_poll_interval,
            solve_circuit_threshold=s.solve_circuit_threshold,
            solve_circuit_probe_seconds=s.solve_circuit_probe_seconds,
            solve_stats_window_seconds=s.solve_stats_window_seconds,
            healthz_cache_ttl=s.healthz_cache_ttl,
            token_prefetch_concurrency=s.token_prefetch_concurrency,
            prefetch_after_solve_delay=s.if_prefetch_after_solve_delay,
            prefetch_ema_alpha=s.if_prefetch_ema_alpha,
        )
