"""P1-A-DAG 深化：LLM 规划器（自然语言 → 多步 DAG 任务）。

把用户的一句话任务分解为可执行的多节点 DAG（scene → 节点序列）：
- Mock 路径（默认，IF_MOCK_UPSTREAM=1）：由 intent 规则推导 scene → 固定节点串
  （scene 根节点 + 可选的终检 critic 节点），零真实 LLM 调用（付费红线）
- 真实 LLM 路径（IF_MOCK_UPSTREAM=0）：调 tryingopen 免费上游分解；
  解析失败 / 无模型 / 无 provider → 回退 Mock，不崩主链路

复用：意图分类走 api/agent/intent（规则正则兜底）；DAG 引擎走 api/agent/dag；
提示词组装走 api/prompts（loader/compose）。三铁律：不重构现有模块，只追加。

开关：IF_AGENT_PLANNER_ENABLED=0 时路由层 404（见 routes/agent_dag.py），
本模块逻辑不受影响。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from ..prompts import compose_system_text

log = logging.getLogger("agent.planner")

# P1-A-DAG 开关：默认开启，回滚置 0 即 404（路由层判定）
IF_PLANNER_ENABLED = os.getenv("IF_AGENT_PLANNER_ENABLED", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Mock 规划时 LLM 占位模型（仅真实路径用；Mock 不触碰 provider）。
# v10.0.0 起真实路径优先读 config 工厂 if_agent_planner_model（IF_PLANNER_LLM_MODEL），
# 运行时环境变量变更在 reset_settings() 后生效——不再用模块级 os.getenv 固化。
PLANNER_LLM_MODEL = os.getenv("IF_PLANNER_LLM_MODEL", "tryingopen/default")


def _resolve_planner_model() -> str:
    """解析 planner 真实 LLM 模型 id：config 工厂优先，缺省回退模块常量。

    修复 v9.0.0 遗留：config `if_agent_planner_model` 定义但从未被使用（见
    《下一步改进指南》§5.3 V5）。走 get_settings() 使测试 reset_settings() 生效。
    """
    try:
        from ..config import get_settings

        model = get_settings().if_agent_planner_model
        return model or PLANNER_LLM_MODEL
    except Exception:
        return PLANNER_LLM_MODEL

# 场景 → 规划节点串（scene 根节点固定 + 场景相关处理节点 + 可选终检）
# 依赖链：根 scene → 场景处理节点 →（可选）critic 终检
PLAN_SCENE_ORDER: list[str] = [
    "image_edit",  # 图生图优先（含"改图"语义，防被 image 先吞）
    "image",
    "video",
    "chat",
    "ecommerce",
    "ppt",
    "unknown",
]

# 每场景追加的处理节点（kind 白名单见 dag.VALID_KINDS）
_SCENE_NODES: dict[str, list[dict[str, Any]]] = {
    "image": [
        {
            "id": "image_generate",
            "kind": "llm",
            "prompt": "根据用户意图生成图像（文生图）。",
        }
    ],
    "image_edit": [
        {
            "id": "image_edit",
            "kind": "llm",
            "prompt": "根据用户意图对已有图像进行编辑（图生图）。",
        }
    ],
    "video": [
        {
            "id": "video_generate",
            "kind": "llm",
            "prompt": "根据用户意图生成视频（文生视频）。",
        }
    ],
    "chat": [
        {
            "id": "chat_reply",
            "kind": "llm",
            "prompt": "根据用户意图进行对话回答。",
        }
    ],
    "ecommerce": [
        {
            "id": "ecommerce_image",
            "kind": "llm",
            "prompt": "根据用户意图生成电商主图/商品图。",
        }
    ],
    "ppt": [
        {
            "id": "ppt_outline",
            "kind": "llm",
            "prompt": "根据用户意图生成 PPT 大纲。",
        }
    ],
}

# 需要终检的场景（critic 审查交付质量）
_CRITIC_SCENES = {"image", "image_edit", "video", "ecommerce"}


def _scene_from_prompt(prompt: str) -> str:
    """由 intent 规则正则推导 scene（复用现有 intent 规则，不重复造轮子）。

    intent._rule_classify 命中即用其 scene；未命中回退 unknown。
    """
    try:
        from .intent import _rule_classify

        result = _rule_classify(prompt)
        if result is not None:
            return result.scene
    except Exception as exc:  # intent 加载失败不崩 planner
        log.warning("intent 规则分类失败，scene 回退 unknown: %s", exc)
    return "unknown"


def _normalize_scene(scene: str | None) -> str:
    """scene 归一：白名单外一律 unknown（安全默认）。"""
    return scene if scene in PLAN_SCENE_ORDER else "unknown"


def _build_mock_plan(prompt: str, scene: str) -> dict[str, Any]:
    """构造 Mock 节点串：scene 根节点 + 场景处理节点 + （可选）critic 终检。"""
    scene = _normalize_scene(scene)
    nodes: list[dict[str, Any]] = [
        {
            "id": "scene",
            "kind": "scene",
            "depends_on": [],
            "prompt": f"识别并确认用户意图场景：{prompt}",
        }
    ]
    prev_id = "scene"
    for extra in _SCENE_NODES.get(scene, []):
        node = {"id": extra["id"], "kind": extra["kind"], "depends_on": [prev_id]}
        if extra.get("prompt"):
            node["prompt"] = extra["prompt"]
        nodes.append(node)
        prev_id = node["id"]
    if scene in _CRITIC_SCENES:
        nodes.append(
            {
                "id": "critic",
                "kind": "critic",
                "depends_on": [prev_id],
                "prompt": "对生成产物做交付质量终检（correctness/procedure/conciseness）。",
            }
        )
    return {
        "nodes": nodes,
        "meta": {
            "scene": scene,
            "mock": True,
            "llm_used": False,
            "model": "",
        },
    }


async def plan_with_mock(prompt: str, scene: str | None = None) -> dict[str, Any]:
    """Mock 规划：纯规则推导，零真实 LLM 调用。"""
    scene = _scene_from_prompt(prompt) if not scene else _normalize_scene(scene)
    return _build_mock_plan(prompt, scene)


async def plan_with_llm(prompt: str, scene: str | None = None) -> dict[str, Any]:
    """真实 LLM 规划（tryingopen 免费上游）。

    付费红线：本函数只调 tryingopen（metered 非付费）+ IF_MOCK_UPSTREAM=0 时启用；
    任何异常/无模型/无 provider/解析失败 → 回退 Mock，不崩主链路。
    """
    mock = os.getenv("IF_MOCK_UPSTREAM", "0").strip().lower() in {"1", "true", "yes", "on"}
    if mock:
        return await plan_with_mock(prompt, scene)

    if not PLANNER_LLM_MODEL:
        log.warning("planner 未配置 LLM 模型，回退 Mock 规划")
        return await plan_with_mock(prompt, scene)

    # v10.0.0：模型 id 走 config 工厂（IF_PLANNER_LLM_MODEL 运行时生效，非模块级固化）
    model_id = _resolve_planner_model()
    if not model_id:
        log.warning("planner 模型为空，回退 Mock 规划")
        return await plan_with_mock(prompt, scene)

    try:
        # importlib 拿**模块本身**（providers/__init__ 包属性 registry 被实例覆盖，
        # `from . import registry` 会绑到单例；模块属性才是测试可 monkeypatch 的位置）
        from importlib import import_module

        from .metrics import inc_llm_call

        _registry_module = import_module("api.providers.registry")
        registry = _registry_module.__dict__.get("registry")
        # 仅在确实没有 registry 单例时才 bootstrap（测试 monkeypatch 后不再触发 bootstrap，
        # 避免 bootstrap 触碰真 registry.providers 破坏注入的 Mock）
        if registry is None:
            from ..providers.registry import bootstrap

            bootstrap()
            registry = _registry_module.__dict__.get("registry")
        if registry is None:
            log.warning("planner 无 registry 单例，回退 Mock")
            return await plan_with_mock(prompt, scene)
        chat_models = registry.all_chat_models()
        if not chat_models:
            log.warning("planner 无可用 chat model，回退 Mock")
            return await plan_with_mock(prompt, scene)

        if model_id not in [m.id for m in chat_models]:
            model_id = chat_models[0].id
        provider = registry.chat_providers.get(model_id.split("/", 1)[0])
        if provider is None:
            log.warning("planner 无对应 provider，回退 Mock")
            return await plan_with_mock(prompt, scene)

        system_prompt = compose_system_text(
            "你是任务规划器。把用户一句话任务分解为多步 DAG，输出 JSON：\n"
            '{"nodes":[{"id":"n1","kind":"llm|critic|tool|scene","depends_on":[],'
            '"prompt":"该步做什么"}]}\n'
            "规则：id 用字母数字_；kind 白名单 llm/critic/tool/scene；depends_on 填前置节点 id；"
            "prompt 用中文写清该步目标。只输出 JSON。",
            None,
        )
        inc_llm_call("planner", "plan")
        result = await provider.chat_collect(
            model_id,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )
        text = result.get("text", "").strip()
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            log.warning("planner LLM 输出非 JSON，回退 Mock")
            return await plan_with_mock(prompt, scene)
        data = json.loads(text[start : end + 1])
        nodes = data.get("nodes") or []
        if not isinstance(nodes, list) or not nodes:
            raise ValueError("planner 未返回节点列表")
        return {
            "nodes": nodes,
            "meta": {
                "scene": _normalize_scene(scene or _scene_from_prompt(prompt)),
                "mock": False,
                "llm_used": True,
                "model": model_id,
            },
        }
    except Exception as exc:
        log.warning("planner LLM 规划失败，回退 Mock: %s", exc)
        return await plan_with_mock(prompt, scene)


async def plan_task(prompt: str, scene: str | None = None) -> dict[str, Any]:
    """规划主入口：Mock 优先，IF_MOCK_UPSTREAM=0 时才走真实 LLM。"""
    mock = os.getenv("IF_MOCK_UPSTREAM", "0").strip().lower() in {"1", "true", "yes", "on"}
    if mock:
        return await plan_with_mock(prompt, scene)
    return await plan_with_llm(prompt, scene)


__all__ = [
    "IF_PLANNER_ENABLED",
    "PLAN_SCENE_ORDER",
    "PLANNER_LLM_MODEL",
    "plan_task",
    "plan_with_llm",
    "plan_with_mock",
]
