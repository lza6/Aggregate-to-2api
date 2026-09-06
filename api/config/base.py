"""config 子模块公共辅助：环境变量布尔/字符串/整数解析 + Settings 级聚合函数。

P0-F1（v8.3）：从 ``__init__.py`` 下沉的 ``_apply_adaptive_defaults`` /
``_validate_settings`` / ``_settings_json`` 聚合函数——依赖 Settings 实例属性但无需
import Settings 类（duck typing，避免循环 import）。
"""

from __future__ import annotations

import os
from typing import Any


def _env_bool(name: str, default: str = "0") -> bool:
    """环境变量布尔解析：'1'/'true'/'yes'/'on' → True；空字符串视为 False。"""
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str = "") -> str:
    """环境变量字符串读取（空值原样返回）。"""
    return os.getenv(name, default)


def _env_int(name: str, default: int = 0) -> int:
    """环境变量整数读取：空字符串或非法值回退默认值，避免 pydantic int 解析崩溃。"""
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def apply_adaptive_defaults(s: Any) -> None:
    """按服务器规格自适应并发参数（仅当用户未显式设置环境变量时）。

    2C2G → worker=4, upstream=12, token=3, queue=1000
    4C4G → worker=8,  upstream=32, token=8,  queue=2000
    4C8G → worker=16, upstream=64, token=16, queue=5000
    8C16G+ → worker=16（封顶）, upstream=64, token=8, queue=5000
    注：worker 自适应仅在未显式设 IF_WORKERS 时生效；IF_WORKER_AUTO 默认关闭，
    故运行期不在 4~16 间动态伸缩，只决定初始 worker 数。
    """
    explicit = bool(
        _env_int("IF_WORKERS")
        or _env_int("IF_UPSTREAM_MAX_INFLIGHT")
        or _env_int("IF_TOKEN_POOL_SIZE")
        or _env_int("IF_MAX_QUEUE")
    )
    if explicit:
        return
    try:
        from ..system_spec import (  # type: ignore[attr-defined]
            ADAPTIVE_MAX_QUEUE,
            ADAPTIVE_TOKEN_POOL_SIZE,
            ADAPTIVE_UPSTREAM_INFLIGHT,
            ADAPTIVE_WORKERS,
        )
    except Exception:
        return
    if s.workers == 10:
        s.workers = ADAPTIVE_WORKERS
    if s.if_upstream_max_inflight == 30:
        s.if_upstream_max_inflight = ADAPTIVE_UPSTREAM_INFLIGHT
    if s.token_pool_size == 6:
        s.token_pool_size = ADAPTIVE_TOKEN_POOL_SIZE
    if s.max_queue == 2000:
        s.max_queue = ADAPTIVE_MAX_QUEUE


def validate_settings(s: Any) -> list[str]:
    """启动时校验关键配置，返回错误列表。"""
    errors: list[str] = []
    if not s.base_url:
        errors.append("BASE_URL（IF_BASE_URL）不能为空")
    if not s.sitekey:
        errors.append("SITEKEY（IF_SITEKEY）不能为空")
    if not s.cf_solver_url:
        errors.append("CF_SOLVER_URL（IF_CF_SOLVER_URL）不能为空")
    if s.port < 1 or s.port > 65535:
        errors.append(f"PORT（IF_PORT）={s.port} 超出有效范围 1-65535")
    if s.max_queue < 1:
        errors.append(f"MAX_QUEUE（IF_MAX_QUEUE）={s.max_queue} 必须 >= 1")
    if s.workers < 1:
        errors.append(f"WORKERS（IF_WORKERS）={s.workers} 必须 >= 1")
    if s.token_pool_size < 1:
        errors.append(f"TOKEN_POOL_SIZE（IF_TOKEN_POOL_SIZE）={s.token_pool_size} 必须 >= 1")
    if s.if_workers_max < s.if_workers_min:
        errors.append(f"IF_WORKERS_MAX（{s.if_workers_max}） < IF_WORKERS_MIN（{s.if_workers_min}）")
    return errors


def settings_json(s: Any) -> dict:
    """导出完整配置快照（供 /v1/meta 扩展）。"""
    return {
        "db": s.db.model_dump(),
        "http": s.http.model_dump(),
        "solver": s.solver.model_dump(),
        "cache": s.cache.model_dump(),
        "provider": s.provider.model_dump(),
        "pool": s.pool.model_dump(),
        "queue": s.queue.model_dump(),
        "observability": s.observability.model_dump(),
        "edit": s.edit.model_dump(),
        "security": s.security.to_env(),
        "chat": {
            "tryingopen_enabled": s.if_tryingopen_enabled,
            "tryingopen_hourly_per_ip": s.if_tryingopen_hourly_per_ip,
            "tryingopen_max_attempts": s.if_tryingopen_max_attempts,
            "tryingopen_sync_minutes": s.if_tryingopen_sync_minutes,
        },
    }
