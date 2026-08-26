"""路由子包：main.py 拆分目标（v4.2）。

main.py 收敛为 app 组装；本包按功能域挂载所有 /v1 端点。
"""
from fastapi import APIRouter

from . import health
from . import tasks
from . import generate
from . import admin
from . import chat

# ── 注册所有路由 ──
api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(tasks.router)
api_router.include_router(generate.router)
api_router.include_router(admin.router)

__all__ = ["api_router"]