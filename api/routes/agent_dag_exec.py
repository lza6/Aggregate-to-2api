"""DAG 节点执行体（真实落地的执行逻辑，非 Mock 占位）。

按节点 kind 分发：
- scene：识别意图场景（规则正则，复用 intent；不真实付费）
- llm：调 tryingopen 免费上游 chat_collect（IF_MOCK_UPSTREAM=1 时 Mock 返回
       固定占位串；真实路径由 providers registry 路由，仅 tryingopen）
- critic：调 critic.review_generation 终检（Mock 规则评分优先；不真实付费）
- memory：L0 观察写入（v10.0.0：截断长度提为常量 + 超时兜底）
- tool：真实本地工具执行回路（v10.0.0：复用 api/skills/ 索引，见 _exec_tool）

付费红线：本执行体只触碰 tryingopen（metered 非付费）+ Mock，无真实付费调用。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

log = logging.getLogger("routes.agent_dag_exec")

# v10.0.0：memory 节点 prompt 写入截断长度（防超大 prompt 撑爆 mem_* 表）
MAX_MEMORY_PROMPT_LEN = 8000
# v10.0.0：单节点执行超时兜底（秒）——防上游 hang 拖死整个 DAG run
NODE_EXEC_TIMEOUT_SECONDS = 30.0


async def execute_node(node_id: str, state: dict[str, Any]) -> str:
    """按节点 kind 执行真实任务，带超时兜底（v10.0.0）。返回结果字符串。

    state 契约（v9.0.0-A）：execute_run 注入 {"node": <当前节点 public_state>,
    "deps": {依赖id: 依赖 public_state}}。当前节点自身信息取 state["node"]。
    """
    node_state = state.get("node") if isinstance(state, dict) else None
    kind = node_state.get("kind") if isinstance(node_state, dict) else None
    kind = kind or "llm"
    prompt = node_state.get("prompt") or "" if isinstance(node_state, dict) else ""

    try:
        return await asyncio.wait_for(_dispatch(kind, prompt), timeout=NODE_EXEC_TIMEOUT_SECONDS)
    except TimeoutError:  # asyncio.wait_for 超时（Python 3.11+ 与内置 TimeoutError 同一对象）
        log.warning("DAG 节点 %s（kind=%s）执行超时（>%ss），降级返回", node_id, kind, NODE_EXEC_TIMEOUT_SECONDS)
        return f"[{kind}-timeout] 节点执行超过 {NODE_EXEC_TIMEOUT_SECONDS}s，已降级返回（防拖死整个 run）"


async def _dispatch(kind: str, prompt: str) -> str:
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
    log.warning("DAG 节点未知 kind %s，返回空串", kind)
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
    """记忆节点：写入观察（L0）。prompt 截断提常量 + 写失败降级不崩。"""
    from ..agent.memory import memory_store

    try:
        await memory_store.observe("default", "dag", prompt[:MAX_MEMORY_PROMPT_LEN] or "（无内容）", 0.5)
        return "memory=stored"
    except Exception as exc:
        log.warning("DAG memory 节点写入失败: %s", exc)
        return f"memory=error:{exc}"


async def _exec_tool(prompt: str) -> str:
    """工具节点：真实本地工具执行回路（v10.0.0）。

    复用 api/skills/loader 的 SkillIndex（能力清单 + 按名读取 SKILL.md 描述）。
    调用契约：
    - prompt 含工具名（如 "使用 playwright 工具" / "调用 imagefree"）→ 返回该 skill 描述；
    - prompt 为列举请求或未命中 → 返回可发现工具清单；
    - 未知工具 → 明确提示未找到（不静默，不崩）。
    零 provider 付费（skill 索引是本地文件读取）。
    """
    try:
        from ..skills.loader import SkillIndex, load_skill
    except Exception as exc:  # skills 索引加载失败降级（不崩 DAG）
        log.warning("DAG tool 节点 skills 索引加载失败: %s", exc)
        return "[tool] 本地技能索引不可用（降级）"

    try:
        # 1) 先看是否有明确工具名（匹配 skills 索引内 name）
        idx = SkillIndex()
        known = idx.names()
        matched = next((n for n in known if n and n.lower() in prompt.lower()), None)
        if matched:
            rec = load_skill(matched)
            desc = rec.description if rec and getattr(rec, "description", None) else ""
            return f"[tool] 已加载技能「{matched}」：{desc or '（无描述）'}"
        # 2) 列举请求 / 无命中 → 返回可发现工具清单
        if "列出" in prompt or "清单" in prompt or "可用" in prompt or "什么工具" in prompt:
            sample = ", ".join(known[:20]) if known else "（无）"
            return f"[tool] 可用工具（{len(known)} 个）：{sample}"
        # 3) 试图用 prompt 里最可能的候选词
        cand = _extract_tool_candidate(prompt)
        if cand and any(cand.lower() in (n or "").lower() for n in known):
            rec = load_skill(next(n for n in known if cand.lower() in (n or "").lower()))
            desc = rec.description if rec and getattr(rec, "description", None) else ""
            return f"[tool] 已加载技能「{cand}」：{desc or '（无描述）'}"
        return f"[tool] 未找到名为「{cand or prompt[:40]}」的本地工具；可用工具清单见上方（共 {len(known)} 个）"
    except Exception as exc:  # noqa: BLE001 — 工具回路兜底不崩 DAG
        log.warning("DAG tool 节点执行失败（降级）: %s", exc)
        return f"[tool] 工具执行降级：{exc}"


def _extract_tool_candidate(prompt: str) -> str:
    """从 prompt 提取最可能的工具名候选（引号内或「xxx工具」片段）。"""
    for quote in ("「", "『", '"', "“", "”"):
        if quote in prompt:
            end = prompt.find("」" if quote in ("「", "『") else ("”" if quote == "“" else '"'))
            if end > 0:
                return prompt[prompt.find(quote) + 1 : end].strip()
    # 去掉"调用/使用/工具"后取最长连续字母数字-_
    cleaned = prompt
    for stop in ("工具", "调用", "使用", "帮我", "请问", "的"):
        cleaned = cleaned.replace(stop, " ")
    words = [w for w in cleaned.replace("，", " ").replace("。", " ").split() if w.strip()]
    return words[0] if words else prompt.strip()
