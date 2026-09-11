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
from typing import Any

from ..config import get_settings

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
        # v11.0.0：IF_MOCK_UPSTREAM=1 时走稳定 Mock（确定性输出，条件分支可验证）
        # P0-2 收敛：mock 开关读 config 工厂 get_settings()（不再裸 os.getenv）
        if get_settings().if_mock_upstream:
            return await _exec_llm_stable(prompt)
        return await _exec_llm(prompt)
    if kind == "critic":
        return await _exec_critic(prompt)
    if kind == "memory":
        return await _exec_memory(prompt)
    if kind == "tool":
        return await _exec_tool(prompt)
    if kind in ("retrieval", "rag"):
        # v11.0.0 RAG 检索节点（复用 api/vector/，SimHash 零依赖，不触碰真实付费上游）
        return await _exec_retrieval(prompt)
    if kind == "image":
        # v11.0.0 多模态节点：Mock 优先（IF_MOCK_UPSTREAM=1 返回占位 URL），真实路径仅 tryingopen
        return await _exec_image(prompt)
    if kind == "human_input":
        # v11.0.0 人机协作节点：默认返回「等待人工确认」（真实 WS 待第二期）
        return await _exec_human_input(prompt)
    log.warning("DAG 节点未知 kind %s，返回空串", kind)
    return ""


async def _exec_retrieval(prompt: str) -> str:
    """RAG 检索节点：复用 VectorStore（SimHash 嵌入 → find_duplicate 相似检索）。

    返回最相似历史任务摘要，供下游节点参考。付费红线：纯本地计算（api/vector/embed 零依赖），
    不触碰任何真实付费上游。
    """
    if not prompt or not prompt.strip():
        return "[retrieval] 缺少检索关键词（prompt 为空）"
    try:
        from ..vector import embed as _embed
        from ..vector.store import get_vector_store

        store = get_vector_store()
        dup = await store.find_duplicate(_embed.compute_embedding(prompt), threshold=0.3)
        if not dup:
            return f"[retrieval] 检索无结果：未找到与「{prompt[:50]}」相似的历史素材"
        sim = round(float(dup.get("similarity", 0.0)), 4)
        return f"[retrieval] 检索到相似素材 t={dup.get('task_id')} sim={sim} hash={dup.get('prompt_hash', '')}"
    except Exception as exc:
        log.warning("DAG retrieval 节点降级: %s", exc)
        return f"[retrieval] 检索降级（{exc}）"


async def _exec_scene(prompt: str) -> str:
    """识别意图场景（复用 intent 规则正则，零成本）。"""
    from ..agent.intent import _rule_classify

    result = _rule_classify(prompt) if prompt else None
    if result is not None:
        return f"scene={result.scene} provider_hint={result.provider_hint}"
    return "scene=unknown"


async def _exec_llm(prompt: str) -> str:
    """调 tryingopen 免费上游 LLM（IF_MOCK_UPSTREAM=1 → Mock 占位）。"""
    from ..config import get_settings

    if get_settings().if_mock_upstream or not prompt:
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


async def _exec_llm_stable(prompt: str) -> str:
    """稳定 Mock 输出（v11.0.0 E2E/测试用）：固定返回含「成功」的结果字符串。

    供 DAG 条件分支等确定性场景使用——真实 tryingopen 输出不确定，条件求值无法稳定验证。
    仅当 IF_MOCK_UPSTREAM=1 时由 execute_node 强制走本函数（测试/E2E 确定性，不真实付费）。
    """
    return f"[llm-mock] 已稳定模拟处理：{prompt[:200]}（结果成功）"


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


async def _exec_image(prompt: str) -> str:
    """多模态图像节点（v11.0.0，Mock 优先）。

    IF_MOCK_UPSTREAM=1（默认）→ 返回占位图 URL（零真实付费）；
    真实路径走 registry 图片 provider（需 provider.generate，Mock 场景不触发）。
    异常降级占位，不崩 DAG。
    """
    from ..config import get_settings

    if get_settings().if_mock_upstream or not prompt:
        _digest = __import__("hashlib").sha1(prompt.encode("utf-8")).hexdigest()[:12]
        return f"[image-mock] 已生成图像占位：https://tingfeng.ai/v1/img/{_digest}.png"
    try:
        from ..agent.budget_guard import assert_can_spend
        from ..providers.registry import bootstrap, registry

        bootstrap()
        models = registry.all_models()
        image_models = [m for m in models if getattr(m, "capabilities", None)]
        if not image_models:
            return "[image-mock] 无可用图像 model（降级占位）"
        spec = image_models[0]
        # v12.0.0 P1-M11：真实付费上游 dispatch 前硬预算门禁（off/observe 模式零行为变化）
        await assert_can_spend(getattr(spec, "provider", "unknown"))
        provider = registry.providers.get(spec.provider)
        if provider is None:
            return "[image-mock] 无对应图像 provider（降级占位）"
        result = await provider.generate(
            spec.id,
            prompt,
            aspect_ratio="1:1",
            resolution="1K",
            download=False,
        )
        return f"[image] 生成结果：{getattr(result, 'url', '') or str(result)[:200]}"
    except Exception as exc:
        log.warning("DAG image 节点执行失败（降级）: %s", exc)
        return f"[image-mock] 图像节点异常降级：{exc}"


async def _exec_human_input(prompt: str) -> str:
    """人机协作节点（v11.0.0，P3 第二期占位）。

    默认返回「等待人工确认」提示；真实 WS 双向通道留待第二期（见《下一步改进指南》§6.2-f）。
    """
    return f"[human] 等待人工确认：{prompt[:200] or '（无提示词）'}"


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
