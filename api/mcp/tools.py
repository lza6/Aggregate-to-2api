"""api/mcp/tools.py — v12.0.0 P1-M1 MCP 工具注册表。

每个工具：name / description / inputSchema（JSON Schema）/ handler(async)。
handler 只复用现有模块能力（三铁律：不重复造轮子）：
- skills_list/skills_get → api.skills.loader
- dag_plan → api.agent.planner.plan_task（Mock 优先零付费）
- dag_status → api.routes.agent_dag_store（内存/SQLite store）
- generate_image → api.routes.agent_dag_exec._exec_image（Mock 优先，付费红线）
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger("mcp.tools")

Handler = Callable[[dict[str, Any]], Awaitable[Any]]


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
    """
    from ..routes.agent_dag_exec import _exec_image

    prompt = str(args.get("prompt", "")).strip()
    if not prompt:
        raise ValueError("prompt 不能为空")
    result = await _exec_image(prompt[:2000])
    return {"result": result}


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
            description=(
                "受控生图（IF_MOCK_UPSTREAM=1 时返回占位 URL 零真实付费；"
                "真实路径走 registry 图像 provider）"
            ),
            input_schema={
                "type": "object",
                "properties": {"prompt": {"type": "string", "description": "生图提示词（≤2000 字）"}},
                "required": ["prompt"],
            },
            handler=_tool_generate_image,
            read_only=False,  # 写语义标注（v12.0.0 无硬门禁，靠 Mock 优先 + 限流兜底）
        ),
    ]


def find_tool(tools: list[McpTool], name: str) -> McpTool | None:
    return next((t for t in tools if t.name == name), None)
