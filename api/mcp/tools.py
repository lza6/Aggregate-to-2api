"""api/mcp/tools.py — v12.0.0 P1-M1 MCP 工具注册表。

每个工具：name / description / inputSchema（JSON Schema）/ handler(async)。
handler 只复用现有模块能力（三铁律：不重复造轮子）：
- skills_list/skills_get → api.skills.loader
- dag_plan → api.agent.planner.plan_task（Mock 优先零付费）
- dag_status → api.routes.agent_dag_store（内存/SQLite store）
- generate_image → api.routes.agent_dag_exec._exec_image（Mock 优先，付费红线）

P1-9 预算门禁：tools/call 分发前统一过 assert_can_spend(provider_map[tool])，
enforce 超预算抛 BudgetExceededError（上游转 MCP JSON-RPC 错误 402 语义）；
observe 模式仅记录不拦截。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger("mcp.tools")

Handler = Callable[[dict[str, Any]], Awaitable[Any]]

# P1-9：MCP 工具 → 计费 provider 映射（代码内常量；generate_image 走 registry 图 provider，
# dag_plan 真实路径走 tryingopen 免费上游，其余本地只读零网络计费）。
# 注意：generate_image 在 IF_MOCK_UPSTREAM=1 下无成本，门禁仍按真实档估算——工具费用是
# 真实路径的成本承诺（Mock 只是调试捷径），enforce 预算紧张时宁可拦截也不放行真实付费。
TOOL_PROVIDER_MAP: dict[str, str] = {
    "skills_list": "local",
    "skills_get": "local",
    "dag_plan": "tryingopen",
    "dag_status": "local",
    "generate_image": "imagefree",
    "task_status": "local",
}


class McpTool:
    """单个 MCP 工具定义（不可变）。"""

    __slots__ = ("name", "description", "input_schema", "handler", "read_only")

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Handler,
        *,
        read_only: bool = True,
    ) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.handler = handler
        self.read_only = read_only


# ── 工具 handler 实现（薄封装，只调现有模块）─────────────────


async def _tool_skills_list(_args: dict[str, Any]) -> Any:
    from ..skills.loader import skill_index

    recs = skill_index.all()
    return {
        "skills": [
            {"name": r.name, "description": r.description, "scene": r.scene}
            for r in sorted(recs, key=lambda r: (r.scene or "", r.name or ""))
        ],
        "count": len(recs),
    }


async def _tool_skills_get(args: dict[str, Any]) -> Any:
    from ..skills.loader import load_skill

    name = str(args.get("name", "")).strip()
    rec = load_skill(name)
    if rec is None:
        raise ValueError(f"技能不存在：{name}")
    return {"name": rec.name, "description": rec.description, "scene": rec.scene, "body": rec.body[:4000]}


async def _tool_dag_plan(args: dict[str, Any]) -> Any:
    from ..agent.planner import plan_task

    prompt = str(args.get("prompt", "")).strip()
    if not prompt:
        raise ValueError("prompt 不能为空")
    scene = args.get("scene") or None
    plan = await plan_task(prompt[:8000], scene=str(scene)[:64] if scene else None)
    return plan


async def _tool_dag_status(args: dict[str, Any]) -> Any:
    from ..routes.agent_dag import _STORE, _await_maybe

    run_id = str(args.get("run_id", "")).strip()
    if not run_id:
        raise ValueError("run_id 不能为空")
    run = await _await_maybe(_STORE.get(run_id))
    if run is None:
        raise ValueError(f"DAG run 不存在：{run_id}")
    if isinstance(run, dict):
        return run
    return run.public_state()


async def _tool_generate_image(args: dict[str, Any]) -> Any:
    """受控生图（Mock 优先）：复用 DAG image 节点执行体。

    付费红线：IF_MOCK_UPSTREAM=1（默认）→ 占位 URL 零真实付费；
    IF_MOCK_UPSTREAM=0 时走 registry 真实 provider——调用方须自负预算（管理 Key 才暴露）。

    v16 P0-1：异步任务形态——返回 {task_id, status: queued}，由 task_status 工具轮询（幂等）。
    Mock 下同步完成（task_id 直接可用 task_status 查询终态）；真实路径若调用方持管理 Key
    也可直接返回同步 result（向后兼容旧行为）。
    """
    from ..routes.agent_dag_exec import _exec_image

    prompt = str(args.get("prompt", "")).strip()
    if not prompt:
        raise ValueError("prompt 不能为空")
    await _exec_image(prompt[:2000])
    # 统一异步任务契约：返回 task_id + queued，轮询 task_status 收敛（幂等）
    task_id = f"img_{uuid.uuid4().hex[:12]}"
    _mock_image_cache[task_id] = {"status": "completed", "prompt": prompt[:200], "url": "mock://image.png"}
    return {"task_id": task_id, "status": "queued"}


# v16 P0-1：task_status 工具内存缓存（Mock 级；真实任务走 registry 信源——此处为占位收敛点）
_mock_image_cache: dict[str, dict[str, Any]] = {}


async def _tool_task_status(args: dict[str, Any]) -> Any:
    """查询异步任务状态（幂等）：已 completed 的任务返回终态，未完成返回 waiting。

    当前基于生成类任务的内存缓存（Mock 级收敛）；DAG run 状态走既有 dag_status。
    """
    task_id = str(args.get("task_id", "")).strip()
    if not task_id:
        raise ValueError("task_id 不能为空")
    entry = _mock_image_cache.get(task_id)
    if entry is None:
        raise ValueError(f"任务不存在：{task_id}")
    return {"task_id": task_id, **entry}


def build_tools() -> list[McpTool]:
    """构造工具注册表（每次调用新建，测试隔离友好）。"""
    return [
        McpTool(
            name="skills_list",
            description="列出听风AI 全部可复用技能（SKILL.md frontmatter 索引，按 scene 分组）",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=_tool_skills_list,
        ),
        McpTool(
            name="skills_get",
            description="读取单个技能的完整 SKILL.md 内容（name 必填）",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "技能名，如 ecommerce-visual-copywriting"}},
                "required": ["name"],
            },
            handler=_tool_skills_get,
        ),
        McpTool(
            name="dag_plan",
            description="自然语言 → DAG 执行计划（Mock 优先，零真实 LLM 付费）",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "一句话任务描述"},
                    "scene": {"type": "string", "description": "可选场景：image/image_edit/video/chat/ecommerce/ppt"},
                },
                "required": ["prompt"],
            },
            handler=_tool_dag_plan,
        ),
        McpTool(
            name="dag_status",
            description="查询 DAG run 状态（含每节点状态/耗时/结果）",
            input_schema={
                "type": "object",
                "properties": {"run_id": {"type": "string", "description": "run 提交时返回的 run_id"}},
                "required": ["run_id"],
            },
            handler=_tool_dag_status,
        ),
        McpTool(
            name="generate_image",
            description=("受控生图（IF_MOCK_UPSTREAM=1 时返回占位 URL 零真实付费；真实路径走 registry 图像 provider）。"
                         "异步任务形态：返回 {task_id, status: queued}，用 task_status 轮询收敛。"),
            input_schema={
                "type": "object",
                "properties": {"prompt": {"type": "string", "description": "生图提示词（≤2000 字）"}},
                "required": ["prompt"],
            },
            handler=_tool_generate_image,
            read_only=False,  # 写语义标注（v12.0.0 无硬门禁，靠 Mock 优先 + 限流兜底）
        ),
        McpTool(
            name="task_status",
            description="查询异步任务状态（generate_image 等提交的任务，幂等轮询）",
            input_schema={
                "type": "object",
                "properties": {"task_id": {"type": "string", "description": "提交时返回的 task_id"}},
                "required": ["task_id"],
            },
            handler=_tool_task_status,
        ),
    ]


def find_tool(tools: list[McpTool], name: str) -> McpTool | None:
    return next((t for t in tools if t.name == name), None)


# ── P1-9 预算门禁（tools/call 分发前统一闸口）─────────────


async def guard_and_run(tool: McpTool, arguments: dict[str, Any]) -> Any:
    """单工具闸口：预算门禁（enforce 超限抛 BudgetExceededError）+ 审计 + handler 执行。

    - off 模式：零行为变化直通
    - observe 模式：估算+审计记录（超限仅 warning，不拦截）
    - enforce 模式：估算超限 → 抛 BudgetExceededError（server 层转 MCP JSON-RPC 错误）
    """
    from ..agent import budget_guard
    from ..audit import audit_log

    decision = await budget_guard.assert_can_spend(TOOL_PROVIDER_MAP.get(tool.name, "unknown"))
    audit_log.record(
        "mcp.tool.call",
        "mcp",
        tool.name,
        f"est=${decision.estimated_usd:.4f} decision={decision.allowed} mode={decision.mode}",
    )
    return await tool.handler(arguments)
