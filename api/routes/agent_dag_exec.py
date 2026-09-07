"""DAG 节点执行体（真实落地的执行逻辑，非 Mock 占位）。

按节点 kind 分发：
- scene：识别意图场景（规则正则，复用 intent；不真实付费）
- llm：调 tryingopen 免费上游 chat_collect（IF_MOCK_UPSTREAM=1 时 Mock 返回
       固定占位串；真实路径由 providers registry 路由，仅 tryingopen）
- critic：调 critic.review_generation 终检（Mock 规则评分优先；不真实付费）
- tool / memory：v9.0.0-B 补本地工具执行回路（当前返回固定说明，不崩）

付费红线：本执行体只触碰 tryingopen（metered 非付费）+ Mock，无真实付费调用。
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger("routes.agent_dag_exec")


async def execute_node(node_id: str, state: dict[str, Any]) -> str:
    """按节点 kind 执行真实任务。返回结果字符串（存入节点 result）。

    state 契约（v9.0.0-A）：execute_run 注入 {"node": <当前节点 public_state>,
    "deps": {依赖id: 依赖 public_state}}。当前节点自身信息取 state["node"]。
    """
    node_state = state.get("node") if isinstance(state, dict) else None
    kind = node_state.get("kind") if isinstance(node_state, dict) else None
    kind = kind or "llm"
    prompt = node_state.get("prompt") or "" if isinstance(node_state, dict) else ""

    if kind == "scene":
        return await _exec_scene(prompt)
    if kind == "llm":
        return await _exec_llm(prompt)
    if kind == "critic":
        return await _exec_critic(prompt)
    if kind == "memory":
        return await _exec_memory(prompt)
    if kind == "tool":
        return await _exec_tool(prompt)
    log.warning("DAG 节点 %s 未知 kind %s，返回空串", node_id, kind)
    return ""


async def _exec_scene(prompt: str) -> str:
    """识别意图场景（复用 intent 规则正则，零成本）。"""
    from ..agent.intent import _rule_classify

    result = _rule_classify(prompt) if prompt else None
    if result is not None:
        return f"scene={result.scene} provider_hint={result.provider_hint}"
    return "scene=unknown"


async def _exec_llm(prompt: str) -> str:
    """调 tryingopen 免费上游 LLM（IF_MOCK_UPSTREAM=1 → Mock 占位）。"""
    mock = os.getenv("IF_MOCK_UPSTREAM", "0").strip().lower() in {"1", "true", "yes", "on"}
    if mock or not prompt:
        return f"[llm-mock] 已模拟处理：{prompt[:200]}"
    try:
        from ..providers.registry import bootstrap, registry

        bootstrap()
        chat_models = registry.all_chat_models()
        if not chat_models:
            return "[llm-mock] 无可用 chat model（降级占位）"
        model_id = chat_models[0].id
        provider = registry.chat_providers.get(model_id.split("/", 1)[0])
        if provider is None:
            return "[llm-mock] 无对应 provider（降级占位）"
        result = await provider.chat_collect(
            model_id,
            [
                {"role": "system", "content": "你是任务执行 Agent，按节点 prompt 完成该步并输出简洁结果。"},
                {"role": "user", "content": prompt},
            ],
        )
        return str(result.get("text", ""))[:1000]
    except Exception as exc:
        log.warning("DAG llm 节点执行失败，降级占位: %s", exc)
        return f"[llm-mock] 执行异常降级：{exc}"


async def _exec_critic(prompt: str) -> str:
    """终检：critic.review_generation（Mock 规则评分优先）。"""
    from ..agent.critic import review_generation

    result = await review_generation(prompt or "（无提示词）", scene="image")
    return f"critic=pass:{result.pass_check} score:{result.score} issues:{','.join(result.issues)}"


async def _exec_memory(prompt: str) -> str:
    """记忆节点：写入观察（L0）。v9.0.0-B 可深化为场景化记忆。"""
    from ..agent.memory import memory_store

    try:
        await memory_store.observe("default", "dag", prompt[:8000] or "（无内容）", 0.5)
        return "memory=stored"
    except Exception as exc:
        log.warning("DAG memory 节点写入失败: %s", exc)
        return f"memory=error:{exc}"


async def _exec_tool(prompt: str) -> str:
    """工具节点：v9.0.0-B 补本地工具执行回路（当前占位）。"""
    return "[tool] 本地工具执行回路将在 v9.0.0-B 开放（当前占位）"
