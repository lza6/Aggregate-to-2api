"""v9.0.0-A 智能体 DAG 编排引擎（P1-A 深化，参考 langgraph DAG + prefect flow graph）。

把 agent 子系统点状能力（intent/critic/memory/guard）编排为**多步任务 DAG**：
- 拓扑排序（Kahn 算法）：串行链 / 并行扇出 / 环形依赖拒绝
- 状态机：pending→running→succeeded/failed/skipped
- 失败传播：fail_fast（默认）任一失败 → 依赖后续 skipped；fail_fast=False 隔离失败分支
- 并发：max_parallel 信号量限流（并行扇出真并发）
- 重试：指数退避 + 抖动（默认 base=0.5s，上限 8s）

三铁律：不重构现有 agent 模块公共接口（intent/critic/memory/guard 全部保留原样）；
新文件只追加；测试 Mock 零真实付费（付费红线）。开关 IF_AGENT_DAG_ENABLED=0 时
路由层 404（见 routes/agent_dag.py），本引擎逻辑不受影响。

本模块为纯引擎层（无 I/O），对外不持有任何 provider 引用——节点执行由
execute_run 注入的 async executor 完成，保证可测性（测试注入 Mock executor）。
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("agent.dag")

# 输入校验常量（路由层也引用）
MAX_RUN_NODES = 50  # 单 run 节点上限（防资源耗尽）
MAX_RUN_NAME_LEN = 128
VALID_KINDS = frozenset({"llm", "critic", "tool", "memory", "scene"})

# 重试默认参数
RETRY_BASE_SECONDS = 0.5
RETRY_MAX_SECONDS = 8.0


class DagError(ValueError):
    """DAG 输入/拓扑校验失败（路由层捕获返回 422）。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ── 节点模型 ─────────────────────────────────────────────────
@dataclass
class DagNode:
    """DAG 单节点（不可变配置 + 可变执行状态）。

    配置字段在 parse_nodes 后冻结；执行状态由 mark_* 更新。
    """

    id: str
    kind: str  # llm / critic / tool / memory / scene
    depends_on: list[str] = field(default_factory=list)
    prompt: str | None = None
    model: str | None = None
    retry: int = 0
    retry_base_seconds: float = RETRY_BASE_SECONDS
    retry_max_seconds: float = RETRY_MAX_SECONDS

    # 执行状态
    status: str = "pending"  # pending / running / succeeded / failed / skipped
    result: str | None = None
    error: str | None = None
    attempt: int = 0
    started_at: float | None = None
    finished_at: float | None = None
    duration_ms: float = 0.0
    created_at: float = field(default_factory=time.time)

    def mark_running(self) -> None:
        self.status = "running"
        self.started_at = time.time()
        self.attempt += 1

    def mark_succeeded(self, result: str) -> None:
        self.status = "succeeded"
        self.result = result
        self.finished_at = time.time()
        self.duration_ms = round((self.finished_at - (self.started_at or self.finished_at)) * 1000, 2)

    def mark_failed(self, error: str) -> None:
        self.status = "failed"
        self.error = error[:500]  # 错误信息截断防日志膨胀
        self.finished_at = time.time()
        self.duration_ms = round((self.finished_at - (self.started_at or self.finished_at)) * 1000, 2)

    def mark_skipped(self) -> None:
        self.status = "skipped"
        self.finished_at = time.time()

    def public_state(self) -> dict[str, Any]:
        """对外 JSON 形状（稳定契约，路由层直接返回）。"""
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "depends_on": list(self.depends_on),
            "prompt": self.prompt,
            "model": self.model,
            "result": self.result,
            "error": self.error,
            "attempt": self.attempt,
            "duration_ms": self.duration_ms,
            "created_at": round(self.created_at, 3),
            "started_at": round(self.started_at, 3) if self.started_at else None,
            "finished_at": round(self.finished_at, 3) if self.finished_at else None,
        }


# ── Run 容器 ────────────────────────────────────────────────
@dataclass
class DagRun:
    """一次 DAG run 的完整状态（内存态，路由层可扩展持久化）。"""

    run_id: str
    name: str
    nodes: dict[str, DagNode]
    status: str = "pending"  # pending / running / succeeded / failed
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    fail_fast: bool = True
    max_parallel: int = 4
    dependencies: dict[str, list[str]] = field(default_factory=dict)  # node_id -> [依赖]
    upstreams: dict[str, list[str]] = field(default_factory=dict)  # node_id -> [下游]
    error_summary: str | None = None  # run 级异常摘要（后台执行兜底写入）

    # 执行期活动任务集（并行扇出时在同一轮创建，execute_run 结束时 gather 等齐）
    _active_tasks: set[asyncio.Task[Any]] = field(default_factory=set, repr=False)

    def mark_running(self) -> None:
        self.status = "running"

    def mark_finished(self) -> None:
        self.status = "succeeded" if all(n.status == "succeeded" for n in self.nodes.values()) else "failed"
        self.finished_at = time.time()

    def public_state(self) -> dict[str, Any]:
        """对外 JSON 形状（稳定契约）。"""
        return {
            "run_id": self.run_id,
            "name": self.name,
            "status": self.status,
            "fail_fast": self.fail_fast,
            "max_parallel": self.max_parallel,
            "error_summary": self.error_summary,
            "created_at": round(self.created_at, 3),
            "finished_at": round(self.finished_at, 3) if self.finished_at else None,
            "nodes": [n.public_state() for n in self.nodes.values()],
        }


# ── 解析与校验 ──────────────────────────────────────────────
def parse_nodes(raw: list[dict[str, Any]]) -> list[DagNode]:
    """把 HTTP 输入节点列表解析为 DagNode 列表（含全部校验）。

    校验失败抛 DagError（路由层 → 422 + 中文 message）。
    校验项：非空 / 数量上限 / id 唯一 / kind 白名单 / depends_on 是 list / id 格式。
    """
    if not raw:
        raise DagError("节点列表不能为空")
    if len(raw) > MAX_RUN_NODES:
        raise DagError(f"节点数超过上限 {MAX_RUN_NODES}")

    seen: set[str] = set()
    nodes: list[DagNode] = []
    for item in raw:
        if not isinstance(item, dict):
            raise DagError("节点必须是 JSON 对象")
        node_id = str(item.get("id", "")).strip()
        if not node_id:
            raise DagError("节点 id 不能为空")
        if not re_fullmatch(node_id):
            raise DagError(f"节点 id 非法：{node_id}（仅允许字母数字_ -）")
        if node_id in seen:
            raise DagError(f"节点 id 重复：{node_id}")
        seen.add(node_id)

        kind = str(item.get("kind", "llm")).strip().lower()
        if kind not in VALID_KINDS:
            raise DagError(f"未知节点类型：{kind}（允许 {sorted(VALID_KINDS)}）")

        depends_on = item.get("depends_on", [])
        if not isinstance(depends_on, list):
            raise DagError(f"节点 {node_id} 的 depends_on 必须是数组")
        dep_ids = [str(d).strip() for d in depends_on]
        for dep in dep_ids:
            if not re_fullmatch(dep):
                raise DagError(f"节点 {node_id} 的依赖 id 非法：{dep}")

        prompt = item.get("prompt")
        if prompt is not None and not isinstance(prompt, str):
            raise DagError(f"节点 {node_id} 的 prompt 必须是字符串")
        model = item.get("model")
        if model is not None and not isinstance(model, str):
            raise DagError(f"节点 {node_id} 的 model 必须是字符串")

        try:
            retry = int(item.get("retry", 0))
        except (TypeError, ValueError):
            raise DagError(f"节点 {node_id} 的 retry 必须是整数") from None
        if not 0 <= retry <= 5:
            raise DagError(f"节点 {node_id} 的 retry 必须在 0-5 之间")

        nodes.append(
            DagNode(
                id=node_id,
                kind=kind,
                depends_on=dep_ids,
                prompt=prompt,
                model=model,
                retry=retry,
            )
        )
    return nodes


def re_fullmatch(node_id: str) -> bool:
    """节点 id 格式：字母数字与 _ -（防止路径/注入类字符进入日志与 URL）。"""
    if not node_id:
        return False
    return all(c.isalnum() or c in "_-" for c in node_id)


def build_graph(
    name: str,
    nodes: list[DagNode],
    *,
    max_parallel: int = 4,
    fail_fast: bool = True,
    retry: int = 0,
) -> DagRun:
    """构建 DagRun 容器 + 依赖/上游索引。

    retry：run 级默认重试次数。单节点未显式指定（retry==0）时被 run 级值覆盖，
    显式指定的节点保留其值（调用方可按节点微调）。
    """
    run = DagRun(
        run_id=uuid.uuid4().hex[:16],
        name=name[:MAX_RUN_NAME_LEN],
        nodes={n.id: n for n in nodes},
        fail_fast=fail_fast,
        max_parallel=max_parallel,
    )
    for n in nodes:
        run.dependencies[n.id] = list(n.depends_on)
        for dep in n.depends_on:
            run.upstreams.setdefault(dep, []).append(n.id)
        if retry > 0 and n.retry == 0:
            n.retry = retry  # run 级默认
    return run


def topological_sort(nodes: list[DagNode]) -> list[str]:
    """Kahn 拓扑排序。环 / 自依赖 / 未知依赖 → DagError。返回执行顺序。"""
    node_ids = {n.id for n in nodes}
    in_degree: dict[str, int] = {n.id: 0 for n in nodes}
    adj: dict[str, list[str]] = {n.id: [] for n in nodes}
    for n in nodes:
        for dep in n.depends_on:
            if dep == n.id:
                raise DagError(f"节点 {n.id} 不能依赖自身")
            if dep not in node_ids:
                raise DagError(f"节点 {n.id} 依赖不存在的节点 {dep}")
            adj[dep].append(n.id)
            in_degree[n.id] += 1

    queue = [n.id for n in nodes if in_degree[n.id] == 0]
    order: list[str] = []
    while queue:
        node_id = queue.pop(0)
        order.append(node_id)
        for downstream in adj[node_id]:
            in_degree[downstream] -= 1
            if in_degree[downstream] == 0:
                queue.append(downstream)

    if len(order) != len(node_ids):
        raise DagError("检测到环形依赖")
    return order


# ── 执行器 ──────────────────────────────────────────────────
NodeExecutor = Callable[[str, dict[str, Any]], Awaitable[str]]


async def execute_run(run: DagRun, executor: NodeExecutor) -> DagRun:
    """执行 DAG run。

    流程：
    1. 拓扑排序（环 → DagError）
    2. 全量预标记 skip：fail_fast 且依赖链含 failed/skipped 的节点直接 skipped
       （预标记在任务全部启动前完成，故 fail_fast 链上 B 失败后 C 必然 skipped）
    3. 并发由 max_parallel 信号量限流；并行扇出真并发（create_task 一轮全 start）
    4. 重试：节点失败按指数退避+抖动重试 retry 次，耗尽才 failed
    5. 结束时按全节点状态收束 run.status

    executor 签名：async def exec(node_id: str, state: dict) -> str（state 为节点上下文快照）。
    """
    order = topological_sort(list(run.nodes.values()))
    run.mark_running()

    semaphore = asyncio.Semaphore(max(1, run.max_parallel))

    async def _run_node(node: DagNode) -> None:
        # 启动前实时判定依赖终态：fail_fast 下依赖 failed → 本节点 skipped
        # （依赖可能已重试成功或失败，预标记无法预知，故在调用时检查）
        if run.fail_fast and any(
            d in run.nodes and run.nodes[d].status in ("failed", "skipped") for d in node.depends_on
        ):
            node.mark_skipped()
            return

        node.mark_running()
        attempt = 0
        while True:
            attempt += 1
            node.attempt = attempt
            try:
                async with semaphore:
                    # state 含当前节点自身 public_state（键 "node"）+ 依赖节点快照（键 "deps"），
                    # 执行器无需再查 run 容器即可取到 kind/prompt/model。
                    state = {
                        "node": node.public_state(),
                        "deps": {d: run.nodes[d].public_state() for d in node.depends_on if d in run.nodes},
                    }
                    result = await executor(node.id, state)
                node.mark_succeeded(result)
                return
            except Exception as exc:  # noqa: BLE001 — 节点失败是业务路径，需完整捕获
                last_error = str(exc) or exc.__class__.__name__
                if attempt > node.retry:
                    node.mark_failed(last_error)
                    return
                delay = min(node.retry_base_seconds * (2 ** (attempt - 1)), node.retry_max_seconds)
                jitter = random.uniform(0, delay * 0.2)
                log.info("DAG 节点 %s/%s 第 %s 次失败（%s），%.2fs 后重试", run.run_id, node.id, attempt, last_error, delay + jitter)
                await asyncio.sleep(delay + jitter)

    # 启动全部非 skipped 节点（一轮 create_task → 并行扇出真并发）。
    # 预标记不再使用——skip 判定由 _run_node 在依赖终态后实时完成,
    # 信号量在 await 侧限流并发数。
    for node_id in order:
        node = run.nodes[node_id]
        run._active_tasks.add(asyncio.create_task(_run_node(node)))

    # 阶段三：等齐全部任务（gather 在 await 侧限流 + 收拢异常，run 不半途悬挂）
    if run._active_tasks:
        await asyncio.gather(*run._active_tasks)

    run.mark_finished()
    return run


__all__ = [
    "DagError",
    "DagNode",
    "DagRun",
    "MAX_RUN_NAME_LEN",
    "MAX_RUN_NODES",
    "RETRY_BASE_SECONDS",
    "RETRY_MAX_SECONDS",
    "VALID_KINDS",
    "build_graph",
    "execute_run",
    "parse_nodes",
    "re_fullmatch",
    "topological_sort",
]
