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


# v10.0.0：DAG run store 双实现切换——IF_DAG_STORE_BACKEND=sqlite（默认）用持久化
# store（重启可查，独立 dag_runs.db），=memory 用原内存实现。DB 异常自动降级内存。
def _build_store() -> Any:
    try:
        from ..config import get_settings

        if get_settings().if_dag_store_backend.lower() == "sqlite":
            from .agent_dag_store_sqlite import DagRunSqliteStore

            return DagRunSqliteStore(get_settings().if_dag_store_db)
    except Exception:
        pass
    return agent_dag_store.dag_run_store


_STORE = _build_store()

router = APIRouter()
log = logging.getLogger("routes.agent_dag")

# DAG 开关（读自 config 工厂；缺省开启，向后兼容现有 agent 子系统）。
# 保持模块级 DAG_ENABLED/PLANNER_ENABLED 兼容旧测试 monkeypatch，但首值取自 get_settings()
def _switches() -> tuple[bool, bool]:
    try:
        from ..config import get_settings

        s = get_settings()
        return bool(s.if_agent_dag_enabled), bool(s.if_agent_planner_enabled)
    except Exception:
        return True, True


_DAG_ENABLED, _PLANNER_ENABLED = _switches()
DAG_ENABLED = _DAG_ENABLED
PLANNER_ENABLED = _PLANNER_ENABLED


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
    await _await_maybe(_STORE.upsert(run))

    # 后台执行（不阻塞 HTTP 响应）；异常记入 run.error_summary
    async def _background() -> None:
        try:
            await _execute_run_safe(run)
        finally:
            await _await_maybe(_STORE.upsert(run))

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


# 双实现兼容桥：sqlite store 方法为 async，内存 store 为 sync（v9.0.0 原实现）。
# _await_maybe 让路由层对两种 store 用同一 async 写法（await 一个非协程会 TypeError）。
async def _await_maybe(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


@router.get("/v1/agent/dag")
async def dag_list(limit: int = 20, status: str | None = None, request: Request = None):
    """DAG run 列表（最近在前）。v10.0.0：Agent 页历史列表 / 运维排障。

    - limit：1-100，默认 20
    - status：可选过滤 pending/running/succeeded/failed/skipped
    - 鉴权：guard_chat_request（公益开放，同 dag_get）
    """
    _dag_enabled_or_404()
    if request is not None:
        auth.guard_chat_request(request)

    limit = max(1, min(int(limit), 100))
    items = await _await_maybe(_STORE.list(limit=limit, status=status))
    # 统一为 public_state dict 形状（sqlite store 已 dict；内存 store 返回 DagRun 对象）
    rows = [r if isinstance(r, dict) else r.public_state() for r in items]
    return {"items": rows, "count": len(rows)}


@router.get("/v1/agent/dag/{run_id}")
async def dag_get(run_id: str, request: Request):
    """查询 DAG run 状态（含每节点状态）。"""
    _dag_enabled_or_404()
    auth.guard_chat_request(request)

    run = await _await_maybe(_STORE.get(run_id))
    if run is None:
        raise AppError(ErrorCodes.NOT_FOUND, "DAG run 不存在", 404)
    # SQLite store 返回 dict（已是 public_state 形状）；内存 store 返回 DagRun 对象
    if isinstance(run, dict):
        return run
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
