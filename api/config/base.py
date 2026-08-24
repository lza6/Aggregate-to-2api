"""config 子模块公共辅助：环境变量布尔/字符串解析。"""
from __future__ import annotations

import os


def _env_bool(name: str, default: str = "0") -> bool:
    """环境变量布尔解析：'1'/'true'/'yes'/'on' → True。"""
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str = "") -> str:
    """环境变量字符串读取（空值原样返回）。"""
    return os.getenv(name, default)