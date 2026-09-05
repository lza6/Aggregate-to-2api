"""tests/test_agent_intent.py — P1-A2 意图分类路由层测试。

验收：
- 规则正则兜底：画图/改图/视频/聊天/电商/PPT 场景命中
- 模糊意图（IF_MOCK_UPSTREAM=1）走 LLM Mock，返回 unknown + 低 confidence + llm_used=True
- 开关 IF_AGENT_INTENT_CLASSIFIER=0 关闭 → 返回 unknown + confidence=0
- confidence 阈值：规则命中 confidence>=0.6 不触发 LLM
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("IF_AGENT_INTENT_CLASSIFIER", "1")
os.environ.setdefault("IF_MOCK_UPSTREAM", "1")


@pytest.mark.asyncio
async def test_rule_classify_image():
    """画图意图命中规则，不触发 LLM。"""
    from api.agent.intent import classify_intent

    r = await classify_intent("帮我画一张猫的图")
    assert r.scene == "image"
    assert r.provider_hint == "imagefree"
    assert r.confidence >= 0.6
    assert r.llm_used is False


@pytest.mark.asyncio
async def test_rule_classify_video():
    """视频意图命中规则。"""
    from api.agent.intent import classify_intent

    r = await classify_intent("生成一段视频")
    assert r.scene == "video"
    assert r.provider_hint == "falai"
    assert r.skill_hint == "critic-review"


@pytest.mark.asyncio
async def test_rule_classify_chat():
    """聊天意图命中规则。"""
    from api.agent.intent import classify_intent

    r = await classify_intent("陪我聊天对话")
    assert r.scene == "chat"
    assert r.provider_hint == "tryingopen"


@pytest.mark.asyncio
async def test_rule_classify_ecommerce():
    """电商意图命中规则。"""
    from api.agent.intent import classify_intent

    r = await classify_intent("画一个电商主图")
    assert r.scene == "ecommerce"


@pytest.mark.asyncio
async def test_rule_classify_image_edit():
    """图生图意图命中规则。"""
    from api.agent.intent import classify_intent

    r = await classify_intent("帮我把这张图改一下")
    assert r.scene == "image_edit"


@pytest.mark.asyncio
async def test_fuzzy_intent_uses_llm_mock():
    """模糊意图（规则未命中）→ 走 LLM Mock，返回 unknown + llm_used=True。"""
    from api.agent.intent import classify_intent

    r = await classify_intent("随便画个东西")  # "随便" 不在规则模式里 → 规则不命中 → LLM
    # Mock 模式返回 unknown + 低 confidence
    assert r.llm_used is True
    assert r.confidence < 0.6


@pytest.mark.asyncio
async def test_disabled_returns_unknown(monkeypatch):
    """IF_AGENT_INTENT_CLASSIFIER=0 → 返回 unknown + confidence=0（零回归）。"""
    import api.agent.intent as intent_mod

    monkeypatch.setattr(intent_mod, "INTENT_CLASSIFIER_ENABLED", False)
    r = await intent_mod.classify_intent("画一张图")
    assert r.scene == "unknown"
    assert r.confidence == 0.0
    assert r.matched_rule == "disabled"


@pytest.mark.asyncio
async def test_intent_result_immutable():
    """IntentResult 是 frozen dataclass（不可变，符合编码规范）。"""
    from api.agent.intent import IntentResult

    r = IntentResult(scene="image", provider_hint="imagefree", skill_hint="", confidence=0.9)
    with pytest.raises((AttributeError, Exception)):
        r.scene = "chat"  # type: ignore[misc]
