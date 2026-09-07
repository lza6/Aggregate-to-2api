"""路由子包：main.py 拆分目标（v4.2）。

main.py 收敛为 app 组装；本包按功能域挂载所有 /v1 端点。
"""

from fastapi import APIRouter

from ..agent import routes as agent_routes
from . import (
    admin,
    agent_dag,  # noqa: F401  (v9.0.0-A DAG 编排：/v1/agent/dag/*)
    chat,
    ecosystem,
    gallery,  # noqa: F401  (P3-D1 向量检索：/v1/gallery/similar)
    generate,
    health,
    security,
    tasks,
)

# ── 注册所有路由 ──
api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(tasks.router)
api_router.include_router(generate.router)
api_router.include_router(admin.router)
api_router.include_router(chat.router)
api_router.include_router(security.router)
api_router.include_router(ecosystem.router)
# v8.1 P1-A：agent 子系统路由（/v1/agent/*），向后兼容不破坏现有端点
api_router.include_router(agent_routes.router)
# v9.0.0-A：智能体 DAG 编排（/v1/agent/dag/run + /plan + /{run_id}），开关关闭时 404
api_router.include_router(agent_dag.router)
# v8.3 P3-D1：画廊相似图检索（/v1/gallery/similar*），依赖 IF_VECTOR_SEARCH_ENABLED=1
api_router.include_router(gallery.router)

__all__ = ["api_router"]
