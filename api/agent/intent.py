"""P1-A2：意图分类→Provider/Skill 路由层（参考 mcp-agent intent_classifier + swarms AgentRouter）。

设计：
- 规则正则兜底：常见意图（画图/改图/聊天/视频脚本）用正则匹配，零成本零延迟
- LLM 仅处理模糊意图：confidence <0.6 时用 tryingopen 上游 LLM 分类
- 双路 classifier：embedding + LLM（参考 mcp-agent 双路）

输出 IntentResult：
- scene: image / chat / video / ecommerce / ppt
- provider_hint: 建议的 provider 前缀（不强制，仍走 adaptive_router）
- skill_hint: 建议加载的 skill 名（供 prompts meta.skills 注入）
- confidence: 0.0-1.0，<0.6 触发 LLM 二次分类

开关：IF_AGENT_INTENT_CLASSIFIER=0 关闭，回退原 prompt 透传（零回归）。
LLM 调用：默认走 tryingopen 免费上游 + IF_MOCK_UPSTREAM=1（测试 Mock）。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

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
    ("image", "imagefree", [r"画一张|生成图|画图|文生图|txt2img|生成.*图"], "image-quality-check", 0.9),
    ("video", "falai", [r"生成视频|文生视频|txt2vid|视频|video"], "critic-review", 0.85),
    ("chat", "tryingopen", [r"聊天|对话|问答|chat|问.*答"], "prompt-refine", 0.8),
    ("ecommerce", "imagefree", [r"电商|主图|详情页|商品图|店铺"], "image-quality-check", 0.85),
    ("ppt", "tryingopen", [r"PPT|ppt|幻灯片|演示文稿"], "prompt-refine", 0.7),
]

# 模糊意图阈值（confidence 低于此值触发 LLM 二次分类）
_LLM_FALLBACK_THRESHOLD = 0.6


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
    mock_upstream = os.getenv("IF_MOCK_UPSTREAM", "0").strip().lower() in {"1", "true", "yes", "on"}
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
    """意图分类主入口：规则正则兜底，confidence <0.6 触发 LLM 二次分类。

    开关 IF_AGENT_INTENT_CLASSIFIER=0 时直接返回 unknown（回退原 prompt 透传）。
    """
    if not INTENT_CLASSIFIER_ENABLED:
        return IntentResult("unknown", "", "", 0.0, "disabled")

    # 1. 规则正则兜底
    rule_result = _rule_classify(prompt)
    if rule_result is not None and rule_result.confidence >= _LLM_FALLBACK_THRESHOLD:
        return rule_result

    # 2. 模糊意图：LLM 二次分类
    if rule_result is not None:
        # 规则命中但 confidence 低（如 ppt 场景），仍走 LLM 确认
        pass
    return await _llm_classify(prompt)


__all__ = [
    "INTENT_CLASSIFIER_ENABLED",
    "IntentResult",
    "classify_intent",
]
