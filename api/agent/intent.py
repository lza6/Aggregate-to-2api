"""P1-A2：意图分类→Provider/Skill 路由层（参考 mcp-agent intent_classifier + swarms AgentRouter）。

设计：
- 规则正则兜底：常见意图（画图/改图/聊天/视频脚本）用正则匹配，零成本零延迟
- embedding 双路：规则未命中时用向量相似度匹配 5 类意图原型（image/video/chat/ecommerce/ppt）
- LLM 兜底：规则 + embedding 均未命中时用 tryingopen 上游 LLM 分类
- 双路 classifier：embedding + LLM（参考 mcp-agent 双路）

输出 IntentResult：
- scene: image / image_edit / chat / video / ecommerce / ppt / unknown
- provider_hint: 建议的 provider 前缀（不强制，仍走 adaptive_router）
- skill_hint: 建议加载的 skill 名（供 prompts meta.skills 注入）
- confidence: 0.0-1.0

开关：IF_AGENT_INTENT_CLASSIFIER=0 关闭，回退原 prompt 透传（零回归）。
LLM 调用：默认走 tryingopen 免费上游 + IF_MOCK_UPSTREAM=1（测试 Mock）。
Embedding 阈值：IF_INTENT_EMBED_THRESHOLD（默认 0.55），低于阈值回退 LLM。
"""

from __future__ import annotations

import base64
import logging
import os
import re
from dataclasses import dataclass, field

from ..vector.embed import compute_embedding, cosine_similarity

log = logging.getLogger("agent.intent")

# P1-A2 开关：默认开启，回滚置 0 即回退原 prompt 透传
INTENT_CLASSIFIER_ENABLED = os.getenv("IF_AGENT_INTENT_CLASSIFIER", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# 意图场景正则规则（规则正则兜底，零成本）
# 参考 mcp-agent intent_classifier 的双路分类：先规则，未命中再 LLM
# 顺序敏感：image_edit 必须在 image 前（"改图/图生图"含"图"会先被 image 命中）
_INTENT_RULES: list[tuple[str, str, list[str], float]] = [
    # (scene, provider_hint, [正则模式], skill_hint, 默认 confidence)
    # image_edit 优先匹配（含"改/编辑/修改 + 图"的语义，避免被 image 的"画图"先吃掉）
    ("image_edit", "imagefree", [r"改图|图生图|img2img|编辑.*图|修改.*图|把.*图.*改"], "image-quality-check", 0.85),
    (
        "image",
        "imagefree",
        [r"画一张|画一只|画图|文生图|txt2img|生成.*图|画.*(猫|狗|人|风景)"],
        "image-quality-check",
        0.9,
    ),
    ("video", "falai", [r"生成视频|文生视频|txt2vid|视频|video"], "critic-review", 0.85),
    ("chat", "tryingopen", [r"聊天|对话|问答|chat|问.*答"], "prompt-refine", 0.8),
    ("ecommerce", "imagefree", [r"电商|主图|详情页|商品图|店铺"], "image-quality-check", 0.85),
    ("ppt", "tryingopen", [r"PPT|ppt|幻灯片|演示文稿"], "prompt-refine", 0.7),
]

# 模糊意图阈值（confidence 低于此值触发 LLM 二次分类，兼容旧语义）
_LLM_FALLBACK_THRESHOLD = 0.6

# ── Embedding 双路（P0-6）─────────────────────────────────────────
# 原型 prompt（中文短句，离线用 compute_embedding 算好 → 固化为 base64 常量，
# 不引入新依赖、不依赖运行时重算）：5 类意图原型。
# 产出方式（已验证 2026-09-15）：
#   from api.vector.embed import compute_embedding, base64  → b64encode(compute_embedding("画一只猫"))
# 常量与 api/vector/embed.py 的 SimHash-256 算法绑定；若该算法变更需重新生成。
_EMBED_PROTO_B64: dict[str, str] = {
    "image": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADNzMw+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAzcxMPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADNzMw+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADNzMw+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM3MzD4AAAAAAAAAAAAAAADNzEw+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM3MTD4AAAAAAAAAAM3MTD4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAzczMPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM3MTD4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==",
    "video": "bBatPgAAAAAAAAAAAAAAAAAAAABsFi0+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABsFi0+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGwWrT4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAbBYtPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGwWrT4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGwWrT4AAAAAAAAAAGwWLT4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGwWLT4AAAAAAAAAAAAAAAAAAAAAAAAAAGwWrT4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGwWLT4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAbBYtPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGwWrT4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAbBatPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==",
    "chat": "H6aYPgAAAAAAAAAAAAAAAAAAAAAfphg+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB+mGD4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAH6aYPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAH6YYPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB+mmD4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAfppg+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAfphg+AAAAAB+mGD4AAAAAH6YYPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB+mmD4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB+mmD4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAH6aYPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAH6aYPgAAAAAfphg+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAH6YYPgAAAAAAAAAAH6YYPgAAAAAAAAAAAAAAAB+mmD4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==",
    "ecommerce": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAU52vPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAU52vPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAU50vPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABTnS8+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABTna8+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAU50vPgAAAAAAAAAAAAAAAFOdrz4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP61Az8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAU50vPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAU52vPgAAAAAAAAAAAAAAAAAAAAAAAAAAU50vPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==",
    "ppt": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAzczMPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM3MTD4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM3MTD8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM3MzD4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==",
}


# 意图原型 → 默认 provider_hint / skill_hint（与规则正则同源，保持路由一致性）
_EMBED_PROTO_META: dict[str, tuple[str, str]] = {
    "image": ("imagefree", "image-quality-check"),
    "video": ("falai", "critic-review"),
    "chat": ("tryingopen", "prompt-refine"),
    "ecommerce": ("imagefree", "image-quality-check"),
    "ppt": ("tryingopen", "prompt-refine"),
}


def _embed_classify(prompt: str) -> IntentResult | None:
    """Embedding 双路分类：与 5 类意图原型做 cosine 相似度。

    最高分 ≥ IF_INTENT_EMBED_THRESHOLD（默认 0.55）时返回对应 IntentResult
    （confidence=相似度，matched_rule="embed:<scene>"），否则返回 None（降级 LLM）。

    异常（embedding 计算/原型解码失败）→ 返回 None，不崩主链路。
    """
    if not prompt:
        return None
    try:
        from ..config import get_settings

        threshold = get_settings().if_intent_embed_threshold
        query_vec = compute_embedding(prompt.strip())
        best_scene: str | None = None
        best_sim = 0.0
        for scene, b64 in _EMBED_PROTO_B64.items():
            proto_vec = base64.b64decode(b64)
            sim = cosine_similarity(query_vec, proto_vec)
            if sim > best_sim:
                best_sim = sim
                best_scene = scene
        if best_scene is None or best_sim < threshold:
            return None
        provider_hint, skill_hint = _EMBED_PROTO_META[best_scene]
        return IntentResult(
            scene=best_scene,
            provider_hint=provider_hint,
            skill_hint=skill_hint,
            confidence=round(best_sim, 4),
            matched_rule=f"embed:{best_scene}",
        )
    except Exception as exc:
        log.warning("embedding 意图分类失败，降级 LLM: %s", exc)
        return None


@dataclass(frozen=True)
class IntentResult:
    """意图分类结果。"""

    scene: str  # image / image_edit / video / chat / ecommerce / ppt / unknown
    provider_hint: str  # 建议的 provider 前缀（不强制）
    skill_hint: str  # 建议加载的 skill 名
    confidence: float  # 0.0-1.0
    matched_rule: str = ""  # 命中的规则模式（debug 用）
    llm_used: bool = False  # 是否用了 LLM 二次分类
    extra: dict = field(default_factory=dict)


def _rule_classify(prompt: str) -> IntentResult | None:
    """规则正则分类。命中返回 IntentResult，未命中返回 None。"""
    if not prompt:
        return None
    text = prompt.strip()
    for scene, provider_hint, patterns, skill_hint, confidence in _INTENT_RULES:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return IntentResult(
                    scene=scene,
                    provider_hint=provider_hint,
                    skill_hint=skill_hint,
                    confidence=confidence,
                    matched_rule=pattern,
                )
    return None


async def _llm_classify(prompt: str) -> IntentResult:
    """LLM 二次分类（模糊意图）。用 tryingopen 免费上游。

    付费 API 红线：本函数用 tryingopen 免费上游 + IF_MOCK_UPSTREAM=1 Mock，
    不发起真实付费调用。用户批准后才可切真实 LLM。
    """
    # 默认 Mock：返回 unknown + 低 confidence（不崩主链路）
    from ..config import get_settings

    mock_upstream = get_settings().if_mock_upstream
    if mock_upstream:
        return IntentResult(
            scene="unknown",
            provider_hint="",
            skill_hint="",
            confidence=0.3,
            matched_rule="llm_mock",
            llm_used=True,
        )
    # 真实 LLM 路径（用户批准后启用）：调 tryingopen 上游分类
    try:
        from ..providers.registry import bootstrap, registry
        from .metrics import inc_intent_classification, inc_llm_call

        bootstrap()
        # 找一个支持 chat 的 tryingopen 模型
        chat_models = registry.all_chat_models()
        if not chat_models:
            inc_intent_classification("fallback")
            return IntentResult("unknown", "", "", 0.3, "llm_no_model", True)
        model_id = chat_models[0].id
        provider = registry.chat_providers.get(model_id.split("/", 1)[0])
        if provider is None:
            inc_intent_classification("fallback")
            return IntentResult("unknown", "", "", 0.3, "llm_no_provider", True)
        system_prompt = (
            "你是意图分类器。把用户 prompt 分类为以下场景之一，只输出 JSON：\n"
            '{"scene":"image|image_edit|video|chat|ecommerce|ppt|unknown",'
            '"provider_hint":"imagefree|falai|tryingopen|",'
            '"skill_hint":"image-quality-check|prompt-refine|critic-review|",'
            '"confidence":0.0-1.0}\n'
            "只输出 JSON，不要其他文字。"
        )
        inc_llm_call("intent", "classify")
        result = await provider.chat_collect(
            model_id,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )
        import json

        text = result.get("text", "").strip()
        # 容错：LLM 可能输出多余文字，提取首个 JSON
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(text[start : end + 1])
            inc_intent_classification("success")
            return IntentResult(
                scene=str(data.get("scene", "unknown")),
                provider_hint=str(data.get("provider_hint", "")),
                skill_hint=str(data.get("skill_hint", "")),
                confidence=float(data.get("confidence", 0.5)),
                matched_rule="llm",
                llm_used=True,
                extra={"raw": text},
            )
        inc_intent_classification("fallback")
    except Exception as exc:
        inc_intent_classification("llm_error")
        log.warning("LLM 意图分类失败，回退 unknown: %s", exc)
    return IntentResult("unknown", "", "", 0.3, "llm_fallback", True)


async def classify_intent(prompt: str) -> IntentResult:
    """意图分类主入口：规则正则 → embedding 双路 → LLM 兜底。

    开关 IF_AGENT_INTENT_CLASSIFIER=0 时直接返回 unknown（回退原 prompt 透传）。
    embedding 命中阈值由 IF_INTENT_EMBED_THRESHOLD（默认 0.55）控制，
    未命中（含异常）自动降级 LLM，不崩主链路。
    """
    if not INTENT_CLASSIFIER_ENABLED:
        return IntentResult("unknown", "", "", 0.0, "disabled")

    # 1. 规则正则兜底
    rule_result = _rule_classify(prompt)
    if rule_result is not None and rule_result.confidence >= _LLM_FALLBACK_THRESHOLD:
        return rule_result

    # 2. Embedding 双路：规则未命中（或规则低置信）时与意图原型做相似度
    if rule_result is None:
        embed_result = _embed_classify(prompt)
        if embed_result is not None:
            return embed_result
        # 3. embedding 未命中 → LLM 兜底（模糊意图）
        return await _llm_classify(prompt)

    # 规则命中但 confidence 低（如 ppt 场景）：先试 embedding 二次确认，
    # 仍未达阈值再走 LLM 确认（与低于 confidence 阈值语义一致）
    embed_result = _embed_classify(prompt)
    if embed_result is not None:
        return embed_result
    return await _llm_classify(prompt)


__all__ = [
    "INTENT_CLASSIFIER_ENABLED",
    "IntentResult",
    "classify_intent",
]
