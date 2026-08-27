"""config 子模块公共辅助：环境变量布尔/字符串/整数解析。"""
from __future__ import annotations

import os


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