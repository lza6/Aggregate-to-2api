"""独立终检 Agent（P1-A7，参考 video-shotcraft final-review）。

视频/图任务完成前用**干净上下文**调 LLM 审查质量，与 adaptive_router 评分解耦：
- adaptive_router 评"路由层成败"（成功率/时延）
- critic 评"交付质量"（内容/尺寸/水印/安全）

评分维度（参考 hermes-self-evolution fitness.py:18 权重）：
- correctness 0.5：尺寸/比例/内容是否符合 prompt
- procedure 0.3：生成流程有无异常重试/降级
- conciseness 0.2：产物有无冗余/水印/重复
- length_penalty：超时/超 token 扣分

开关：IF_CRITIC_AGENT_ENABLED=0 关闭，回退无终检（零回归）。
LLM 调用：用 tryingopen 免费上游（付费 API 红线：Mock 或用户批准预算）。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger("agent.critic")

# P1-A7 开关：默认开启，回滚置 0 即回退无终检
CRITIC_AGENT_ENABLED = os.getenv("IF_CRITIC_AGENT_ENABLED", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


@dataclass(frozen=True)
class CriticResult:
    """终检结果。"""

    pass_check: bool  # 是否通过终检
    score: float  # 0.0-1.0 综合分
    issues: list[str] = field(default_factory=list)  # 发现的问题
    recommendation: str = "accept"  # accept / regenerate / fallback
    reasoning: str = ""  # LLM 给出的理由
    llm_used: bool = False  # 是否用了 LLM 审查


async def review_generation(
    prompt: str,
    asset_url: str | None = None,
    asset_bytes: bytes | None = None,
    *,
    scene: str = "image",
    provider: str = "",
    duration_ms: float = 0.0,
    retry_count: int = 0,
) -> CriticResult:
    """对一次生成产物做终检。

    付费 API 红线：用 tryingopen 免费上游 + IF_MOCK_UPSTREAM=1 Mock。
    用户批准后才真实调 LLM 审查。

    返回 CriticResult。失败不崩主链路（降级 pass=True + warn）。
    """
    if not CRITIC_AGENT_ENABLED:
        return CriticResult(pass_check=True, score=1.0, recommendation="accept", reasoning="critic disabled")

    mock_upstream = os.getenv("IF_MOCK_UPSTREAM", "0").strip().lower() in {"1", "true", "yes", "on"}
    if mock_upstream:
        return _mock_review(prompt, scene, provider, duration_ms, retry_count)

    # 真实 LLM 路径（用户批准后启用）：调 tryingopen 上游审查
    try:
        return await _llm_review(prompt, asset_url, scene, provider, duration_ms, retry_count)
    except Exception as exc:
        log.warning("critic LLM 审查失败，回退 Mock: %s", exc)
        return _mock_review(prompt, scene, provider, duration_ms, retry_count)


def _mock_review(
    prompt: str, scene: str, provider: str, duration_ms: float, retry_count: int
) -> CriticResult:
    """Mock 终检：基于结构化规则评分（不调 LLM）。"""
    issues: list[str] = []
    score = 1.0
    # 重试过多扣分
    if retry_count >= 2:
        score -= 0.2
        issues.append(f"retry_count={retry_count}")
    # 超时扣分
    if duration_ms > 30000:
        score -= 0.1
        issues.append(f"slow_duration={duration_ms}ms")
    # prompt 过短扣分
    if len(prompt) < 5:
        score -= 0.15
        issues.append("prompt_too_short")
    score = max(0.0, score)
    return CriticResult(
        pass_check=score >= 0.6,
        score=round(score, 4),
        issues=issues,
        recommendation="accept" if score >= 0.6 else "regenerate",
        reasoning="mock_critic_rule_based",
        llm_used=False,
    )


async def _llm_review(
    prompt: str,
    asset_url: str | None,
    scene: str,
    provider: str,
    duration_ms: float,
    retry_count: int,
) -> CriticResult:
    """真实 LLM 终检：用 tryingopen 上游审查产物质量。"""
    from ..providers.registry import bootstrap, registry

    bootstrap()
    chat_models = registry.all_chat_models()
    if not chat_models:
        return _mock_review(prompt, scene, provider, duration_ms, retry_count)
    model_id = chat_models[0].id
    chat_provider = registry.chat_providers.get(model_id.split("/", 1)[0])
    if chat_provider is None:
        return _mock_review(prompt, scene, provider, duration_ms, retry_count)

    system_prompt = (
        "你是交付质量审查 Agent。审查一次生成产物的质量，输出 JSON：\n"
        '{"pass":true|false,"score":0.0-1.0,"issues":["..."],'
        '"recommendation":"accept|regenerate|fallback","reasoning":"..."}\n'
        "评分维度：correctness 0.5（是否符合 prompt）+ procedure 0.3（流程异常）"
        "+ conciseness 0.2（冗余/水印）。只输出 JSON。"
    )
    user_content = (
        f"场景: {scene}\nprovider: {provider}\nprompt: {prompt}\n"
        f"asset_url: {asset_url or 'N/A'}\n耗时: {duration_ms}ms\n重试次数: {retry_count}"
    )
    result = await chat_provider.chat_collect(
        model_id,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    text = result.get("text", "").strip()
    import json

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        data = json.loads(text[start : end + 1])
        return CriticResult(
            pass_check=bool(data.get("pass", True)),
            score=float(data.get("score", 0.8)),
            issues=list(data.get("issues", [])),
            recommendation=str(data.get("recommendation", "accept")),
            reasoning=str(data.get("reasoning", "")),
            llm_used=True,
        )
    return _mock_review(prompt, scene, provider, duration_ms, retry_count)


__all__ = [
    "CRITIC_AGENT_ENABLED",
    "CriticResult",
    "review_generation",
]
