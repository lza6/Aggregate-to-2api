"""DAG 编排路由（v9.0.0-A）：/v1/agent/dag/* 端点。

新增端点（向后兼容，不破坏现有 /v1/agent/*）：
- POST /v1/agent/dag/run           提交 DAG run（节点/依赖/fail_fast/max_parallel/retry）
- GET  /v1/agent/dag/{run_id}      查询 run 状态（含每节点状态 + 节点级执行轨迹）
- POST /v1/agent/dag/plan          自然语言 → DAG（LLM 规划器，Mock 优先）
- POST /v1/agent/dag/{run_id}/resume  续跑非终态/failed/skipped 节点（幂等；开关缺省关）

鉴权：复用 auth.guard_dag_request（v11.0.0：chat 频控 + DAG 独立限流 S-1；公益开放同生图）。
开关：IF_AGENT_DAG_ENABLED=0 → 404；IF_AGENT_PLANNER_ENABLED=0 → plan 404；
      IF_DAG_RESUME_ENABLED=0（缺省）→ resume 404。
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
RESUME_ENABLED = True  # v13 P0-7 初始 True，端点内用 get_settings().if_dag_resume_enabled 实时判定


def _resume_enabled() -> bool:
    """v13 P0-7：resume 开关读 config 工厂（IF_DAG_RESUME_ENABLED，缺省关）。

    monkeypatch.setenv + reset_settings() 后生效；DAG_ENABLED 走模块级快照兼容旧测试。
    """
    try:
        from ..config import get_settings

        return bool(get_settings().if_dag_resume_enabled)
    except Exception:
        return False


# ── 请求模型 ────────────────────────────────────────────────
class DagNodeInput(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    kind: str = Field("llm", max_length=16)
    depends_on: list[str] = Field(default_factory=list)
    prompt: str | None = Field(None, max_length=8000)
    model: str | None = Field(None, max_length=128)
    retry: int = Field(0, ge=0, le=5)
    # v11.0.0 条件分支：形如 "A contains 成功" / "B equals 完成"（白名单操作符）
    condition: str | None = Field(None, max_length=200)


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
    auth.guard_chat_request(request)  # 频控走 chat 基线（公益开放）
    from ..auth import check_dag_rate_limit

    check_dag_rate_limit(request)  # v11.0.0 S-1 独立 DAG 限流

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

    # 后台执行（不阻塞 HTTP 响应）；异常记入 run.error_summary；
    # v11.0.0 跨 run 记忆：run 结束把结果摘要沉淀 L0（复用 memory.memory_store.observe）
    async def _background() -> None:
        try:
            # v13 P0-7：挂节点终态轨迹回调（G 节点终态即持久化，运行中 GET 亦可渐进看到）
            await _execute_run_safe(run, on_trace=_store_trace_callback)
        finally:
            await _persist_run_memory(run)
            # v18 P0-1：技能自动沉淀（IF_SKILL_SEDIMENT_AUTO=1 时对 succeeded run 生成候选草稿，
            # 内部四重前置检查 + 扫描闸门 + 重放验证；失败静默降级不阻塞后台）
            try:
                from ..agent.skill_sediment_auto import maybe_sediment_run

                await maybe_sediment_run(run)
            except Exception as exc:  # noqa: BLE001 - 自动沉淀是增强能力，失败不崩后台
                log.warning("DAG run 自动沉淀失败（降级）: %s", exc)
            await _await_maybe(_STORE.upsert(run))

    from ..background import spawn

    spawn(_background(), name=f"dag-run-{run.run_id}")

    return {"run_id": run.run_id, "status": run.status}


async def _execute_run_safe(run, *, on_trace=None, resume: bool = False) -> None:
    """执行 DAG run（内部异常记入 run，不崩 worker）。

    v13 P0-7 纯增量参数：
    - on_trace：节点终态轨迹回调（持久化 node_traces）
    - resume：续跑模式（非 succeeded 节点重置 pending 重跑，幂等）
    """
    from ..agent.dag import execute_run

    try:
        await execute_run(run, _execute_node, on_trace=on_trace, resume=resume)
    except Exception as exc:  # noqa: BLE001 — 后台执行兜底，不崩 worker
        run.status = "failed"
        run.error_summary = str(exc)[:500]
        run.finished_at = time.time()
        log.error("DAG run %s 执行失败: %s", run.run_id, exc)


async def _persist_run_memory(run) -> None:
    """run 结束沉淀跨 run 记忆（v11.0.0 6.2-e）。

    IF_MEMORY_CONSOLIDATION_ENABLED=1 时把 run 结果摘要 + 成败模式写入 L0 观察，
    供后续 run/chat 复用。观察写入失败仅记 warning，不崩后台任务。
    """
    try:
        from ..config import get_settings

        if not get_settings().if_memory_consolidation_enabled:
            return
        from ..agent.memory import memory_store

        status = run.status
        summary = f"dag run {run.status}: nodes ops " + ",".join(f"{n.status}" for n in run.nodes.values())
        await memory_store.observe(
            "dag",
            "dag",
            f"{run.name} {status} [{summary}]"[:800],
            importance=0.6 if status == "succeeded" else 0.8,
        )
    except Exception as exc:  # noqa: BLE001 — 记忆沉淀是增强能力，失败不崩后台
        log.warning("DAG run 记忆沉淀失败（降级）: %s", exc)


# 双实现兼容桥：sqlite store 方法为 async，内存 store 为 sync（v9.0.0 原实现）。
# _await_maybe 让路由层对两种 store 用同一 async 写法（await 一个非协程会 TypeError）。
async def _await_maybe(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


async def _store_trace_callback(trace: dict[str, Any]) -> None:
    """v13 P0-7：节点终态轨迹回调 → 写入 store（sqlite 落 node_traces，内存静默跳过）。

    挂到 execute_run 的 on_trace；回调异常由 _STORE.append_trace 内部捕获降级。
    """
    append = getattr(_STORE, "append_trace", None)
    if append is not None:
        await _await_maybe(append(trace))


@router.get("/v1/agent/dag")
async def dag_list(limit: int = 20, status: str | None = None, request: Request = None):
    """DAG run 列表（最近在前）。v10.0.0：Agent 页历史列表 / 运维排障。

    - limit：1-100，默认 20
    - status：可选过滤 pending/running/succeeded/failed/skipped
    - 鉴权：guard_chat_request（公益开放；读操作不占用 DAG 写限流额度）
    """
    _dag_enabled_or_404()
    if request is not None:
        auth.guard_chat_request(request)

    limit = max(1, min(int(limit), 100))
    items = await _await_maybe(_STORE.list(limit=limit, status=status))
    # 统一为 public_state dict 形状（sqlite store 已 dict；内存 store 返回 DagRun 对象）
    rows = [r if isinstance(r, dict) else r.public_state() for r in items]
    # v20.3.8（真实缺口修复）：列表端点与详情端点一致，每 run 节点附加教学化 explain——
    # 管理台 RunCard 用列表数据渲染节点，此前 explain 缺失导致 UI 展示不了教学化释义
    for row in rows:
        _attach_explain(row)
    return {"items": rows, "count": len(rows)}


@router.get("/v1/agent/dag/{run_id}")
async def dag_get(run_id: str, request: Request):
    """查询 DAG run 状态（含每节点状态）。

    v20.3.3 P2（终局审计闭环）：把 explain_templates 教学化释义真接线——
    IF_AGENT_EXPLAIN_ENABLED=1（缺省）时，每节点附加 `explain` 字段（what/why/io 大白话），
    供门户/管理台展示「为什么这样规划」。向后兼容：新增字段不破坏现有契约。
    """
    _dag_enabled_or_404()
    auth.guard_chat_request(request)  # 读操作不占用 DAG 写限流额度

    run = await _await_maybe(_STORE.get(run_id))
    if run is None:
        raise AppError(ErrorCodes.NOT_FOUND, "DAG run 不存在", 404)
    # SQLite store 返回 dict（已是 public_state 形状）；内存 store 返回 DagRun 对象
    data = run if isinstance(run, dict) else run.public_state()
    # v20.3.3 P2：教学化释义接线（缺省开；IF_AGENT_EXPLAIN_ENABLED=0 关闭零行为变化）
    _attach_explain(data)
    return data


def _attach_explain(data: dict) -> None:
    """给 DAG run 的每节点附加 explain 教学化释义（受 IF_AGENT_EXPLAIN_ENABLED 控制）。"""
    try:
        from ..config import get_settings

        if not getattr(get_settings(), "if_agent_explain_enabled", True):
            return
    except Exception:
        return
    try:
        from ..agent.explain_templates import build_node_explain

        nodes = data.get("nodes")
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            kind = node.get("kind") or "llm"
            node["explain"] = build_node_explain(kind, node)
    except Exception:
        # 教学化是增强信息，失败静默不影响主链路
        return


@router.post("/v1/agent/dag/{run_id}/resume")
async def dag_resume(run_id: str, request: Request):
    """续跑一个非终态 / failed / skipped 的 DAG run（v13 P0-7）。

    幂等语义：已 succeeded 节点不重跑（attempt 保留原值，计数器可验证）；其余节点
    （pending/running/failed/skipped）重置为 pending 后整图重跑。复用 run_id，
    前台 GET 同一 run_id 即可看到续跑后的节点轨迹追加（node_traces append-only）。
    开关 IF_DAG_RESUME_ENABLED=0（缺省 0）→ 404。
    """
    _dag_enabled_or_404()
    if not _resume_enabled():
        raise HTTPException(status_code=404, detail="DAG 续跑未启用（IF_DAG_RESUME_ENABLED=0）")
    auth.guard_chat_request(request)  # 频控走 chat 基线（公益开放）
    from ..auth import check_dag_rate_limit

    check_dag_rate_limit(request)  # v11.0.0 S-1 独立 DAG 限流

    run = await _await_maybe(_STORE.get(run_id))
    if run is None:
        raise AppError(ErrorCodes.NOT_FOUND, "DAG run 不存在", 404)

    # 内存 store 返回 DagRun 对象（可续跑）；sqlite store 返回 dict 快照（无
    # execute_run 可操作的内存节点状态机）。v14 P2：sqlite 后端先 restore_run
    # 反序列化为 DagRun 对象（节状态+依赖索引完整还原），走同一续跑路径；
    # restore_run 失败/快照缺失 → 404（不伪装不可执行路径）。
    if not hasattr(run, "nodes"):
        restore = getattr(_STORE, "restore_run", None)
        if restore is None:
            raise AppError(ErrorCodes.BAD_REQUEST, "当前 DAG store 后端不支持续跑（仅内存/持久化后端可续跑）", 400)
        dagrun = await _await_maybe(restore(run_id))
        if dagrun is None:
            raise AppError(ErrorCodes.NOT_FOUND, "DAG run 不存在", 404)
        run = dagrun

    # 全部节点已 succeeded → 无续跑必要（幂等边界：避免无谓重跑）
    if all(n.status == "succeeded" for n in run.nodes.values()):
        await _await_maybe(_STORE.upsert(run))
        return {"run_id": run.run_id, "status": run.status, "resumed": False}

    # 终态 run（已 succeeded/failed）中仍有非 succeeded 节点 → 续跑必要
    async def _background() -> None:
        try:
            await _execute_run_safe(run, on_trace=_store_trace_callback, resume=True)
        finally:
            await _persist_run_memory(run)
            # v18 P0-1：技能自动沉淀（IF_SKILL_SEDIMENT_AUTO=1 时对 succeeded run 生成候选草稿，
            # 内部四重前置检查 + 扫描闸门 + 重放验证；失败静默降级不阻塞后台）
            try:
                from ..agent.skill_sediment_auto import maybe_sediment_run

                await maybe_sediment_run(run)
            except Exception as exc:  # noqa: BLE001 - 自动沉淀是增强能力，失败不崩后台
                log.warning("DAG run 自动沉淀失败（降级）: %s", exc)
            await _await_maybe(_STORE.upsert(run))

    from ..background import spawn

    spawn(_background(), name=f"dag-resume-{run.run_id}")
    return {"run_id": run.run_id, "status": "running", "resumed": True}


@router.post("/v1/agent/dag/plan")
async def dag_plan(payload: DagPlanRequest, request: Request):
    """自然语言 → DAG 节点列表（LLM 规划器，Mock 优先）。"""
    _dag_enabled_or_404()
    _planner_enabled_or_404()
    auth.guard_chat_request(request)  # 规划是只读推导，不占用 DAG 写限流额度

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
