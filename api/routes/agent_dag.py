"""DAG 编排路由（v9.0.0-A）：/v1/agent/dag/* 端点。

新增端点（向后兼容，不破坏现有 /v1/agent/*）：
- POST /v1/agent/dag/run      提交 DAG run（节点/依赖/fail_fast/max_parallel/retry）
- GET  /v1/agent/dag/{run_id} 查询 run 状态（含每节点状态）
- POST /v1/agent/dag/plan     自然语言 → DAG（LLM 规划器，Mock 优先）

鉴权：复用 auth.guard_chat_request（与 chat 端点同 Key；公益开放同生图）。
开关：IF_AGENT_DAG_ENABLED=0 → 404；IF_AGENT_PLANNER_ENABLED=0 → plan 404。
三铁律：不重构现有 agent 模块；只追加；Mock 优先零真实付费。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import auth
from ..errors import AppError, ErrorCodes
from . import agent_dag_store  # 模块级内存 run 存储（进程内，重启即清）

# 直接用 store 实例（模块属性 upsert/get 被包级属性遮蔽，避免 `from . import`
# 再吃一次包单例解析问题——cerebrum 教训：模块 attr 优先取实例方法）
_STORE = agent_dag_store.dag_run_store

router = APIRouter()
log = logging.getLogger("routes.agent_dag")

# DAG 开关（读自环境变量；缺省开启，向后兼容现有 agent 子系统）
DAG_ENABLED = __import__("os").getenv("IF_AGENT_DAG_ENABLED", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# planner 开关
PLANNER_ENABLED = __import__("os").getenv("IF_AGENT_PLANNER_ENABLED", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


# ── 请求模型 ────────────────────────────────────────────────
class DagNodeInput(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    kind: str = Field("llm", max_length=16)
    depends_on: list[str] = Field(default_factory=list)
    prompt: str | None = Field(None, max_length=8000)
    model: str | None = Field(None, max_length=128)
    retry: int = Field(0, ge=0, le=5)


class DagRunRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    nodes: list[DagNodeInput] = Field(..., min_length=1)
    fail_fast: bool = Field(True)
    max_parallel: int = Field(4, ge=1, le=16)
    retry: int = Field(0, ge=0, le=5)


class DagPlanRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    scene: str | None = Field(None, max_length=64)


# ── 节点执行器（真实落地的 DAG 执行体）───────────────────────
async def _execute_node(node_id: str, state: dict[str, Any]) -> str:
    """按节点 kind 执行真实任务（非 Mock 占位）。

    - scene：识别意图场景（规则正则，复用 intent）
    - llm：调 tryingopen 免费上游 chat_collect（IF_MOCK_UPSTREAM=1 时 Mock 返回占位）
    - critic：调 critic.review_generation 终检（Mock 规则评分，不真实付费）
    - tool / memory：占位（v9.0.0-B 补本地工具执行回路）
    """
    from .agent_dag_exec import execute_node as _real_execute

    return await _real_execute(node_id, state)


def _dag_enabled_or_404() -> None:
    """IF_AGENT_DAG_ENABLED=0 → 404（开关关闭）。"""
    if not DAG_ENABLED:
        raise HTTPException(status_code=404, detail="DAG 编排已关闭（IF_AGENT_DAG_ENABLED=0）")


def _planner_enabled_or_404() -> None:
    """IF_AGENT_PLANNER_ENABLED=0 → 404（规划器关闭）。"""
    if not PLANNER_ENABLED:
        raise HTTPException(status_code=404, detail="DAG 规划器已关闭（IF_AGENT_PLANNER_ENABLED=0）")


# ── 端点 ────────────────────────────────────────────────────
@router.post("/v1/agent/dag/run")
async def dag_run(payload: DagRunRequest, request: Request):
    """提交 DAG run：解析节点 → 拓扑校验 → 后台执行 → 返回 run_id。"""
    _dag_enabled_or_404()
    auth.guard_chat_request(request)

    from ..agent.dag import DagError, build_graph, parse_nodes

    try:
        nodes = parse_nodes([n.model_dump() for n in payload.nodes])
    except DagError as exc:
        raise AppError(ErrorCodes.BAD_REQUEST, exc.message, 422) from None

    try:
        run = build_graph(
            payload.name,
            nodes,
            max_parallel=payload.max_parallel,
            fail_fast=payload.fail_fast,
            retry=payload.retry,
        )
    except DagError as exc:
        raise AppError(ErrorCodes.BAD_REQUEST, exc.message, 422) from None

    # 提交时即做拓扑校验（环/自依赖/未知依赖 → 422），不等后台执行才失败
    from ..agent.dag import topological_sort

    try:
        topological_sort(list(run.nodes.values()))
    except DagError as exc:
        raise AppError(ErrorCodes.BAD_REQUEST, exc.message, 422) from None

    # 注册 run（先注册后执行，保证 GET 立即可见）
    _STORE.upsert(run)

    # 后台执行（不阻塞 HTTP 响应）；异常记入 run.error_summary
    async def _background() -> None:
        try:
            await _execute_run_safe(run)
        finally:
            _STORE.upsert(run)

    from ..background import spawn

    spawn(_background(), name=f"dag-run-{run.run_id}")

    return {"run_id": run.run_id, "status": run.status}


async def _execute_run_safe(run) -> None:
    """执行 DAG run（内部异常记入 run，不崩 worker）。"""
    from ..agent.dag import execute_run

    try:
        await execute_run(run, _execute_node)
    except Exception as exc:  # noqa: BLE001 — 后台执行兜底，不崩 worker
        run.status = "failed"
        run.error_summary = str(exc)[:500]
        run.finished_at = time.time()
        log.error("DAG run %s 执行失败: %s", run.run_id, exc)


@router.get("/v1/agent/dag/{run_id}")
async def dag_get(run_id: str, request: Request):
    """查询 DAG run 状态（含每节点状态）。"""
    _dag_enabled_or_404()
    auth.guard_chat_request(request)

    run = _STORE.get(run_id)
    if run is None:
        raise AppError(ErrorCodes.NOT_FOUND, "DAG run 不存在", 404)
    return run.public_state()


@router.post("/v1/agent/dag/plan")
async def dag_plan(payload: DagPlanRequest, request: Request):
    """自然语言 → DAG 节点列表（LLM 规划器，Mock 优先）。"""
    _dag_enabled_or_404()
    _planner_enabled_or_404()
    auth.guard_chat_request(request)

    from ..agent.planner import plan_task

    plan = await plan_task(payload.prompt, scene=payload.scene)
    # 校验规划节点合法性（不合法仍返回，调用方可自行决定是否提交 run）
    try:
        from ..agent.dag import parse_nodes

        parse_nodes(plan["nodes"])
        plan["meta"]["valid"] = True
    except Exception:
        plan["meta"]["valid"] = False
    return plan


__all__ = ["router"]
