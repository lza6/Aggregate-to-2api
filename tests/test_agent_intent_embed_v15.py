"""tests/test_agent_intent_embed_v15.py — v15-A 意图分类 Embedding 多原型语义增强测试。

验收：
- 6 类场景（image/video/chat/ecommerce/ppt/image_edit）各 ≥1 个「含 _EMBED_PROTO_EXTRAS
  关键词」的 prompt 命中对应 scene 且 confidence >= IF_INTENT_EMBED_THRESHOLD（0.55）
- 不含任何关键词的模糊 prompt → embedding 返回 None / classify_intent 降级 LLM Mock
- IF_AGENT_INTENT_CLASSIFIER=0 关闭 → 返回 unknown + confidence=0
- 关键词加权：命中关键词的子串加分 0.15 把 borderline 拉过阈值；未命中关键词时阈值不变
- 单原型 + 扩展原型全失（_EMBED_PROTO_EXTRAS 置空 + 模糊 prompt）→ None，且
  规则已命中仍优先（v14 语义：'画一只猫' 走规则 image，不受 embedding 改动影响）

约束：所有测试 Mock（IF_MOCK_UPSTREAM=1，LLM 兜底走 tryingopen 免费上游 Mock，
不发起真实付费调用）；monkeypatch.setenv 后必须 reset_settings()。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("IF_AGENT_INTENT_CLASSIFIER", "1")
os.environ.setdefault("IF_MOCK_UPSTREAM", "1")

# 6 场景关键词 prompt：均只含对应 scene 的 _EMBED_PROTO_EXTRAS 关键词、
# 不命中 _INTENT_RULES 规则（验证 embedding 多原型 + 加权路径而非规则兜底）
_KEYWORD_PROMPTS: dict[str, str] = {
    "image": "我想要一张好看的图片",  # 含"图片"
    "video": "我要看动画片",  # 含"动画"
    "chat": "帮我写一段文字",  # 含"写"
    "ecommerce": "我想买这个商品",  # 含"商品"
    "ppt": "帮我做个演示",  # 含"演示"
    "image_edit": "帮我修图",  # 含"修图"
}


def _embed_classify_direct(prompt: str):
    """直调 _embed_classify（绕过规则正则，验证 embedding 多原型路径本身）。"""
    from api.agent.intent import _embed_classify

    return _embed_classify(prompt)


@pytest.mark.asyncio
async def test_keyword_prompt_hits_each_scene():
    """6 场景含关键词 prompt 直调 _embed_classify 均命中对应 scene 且 confidence >= 0.55。"""
    from api.config import get_settings, reset_settings

    reset_settings()
    threshold = get_settings().if_intent_embed_threshold
    assert threshold == 0.55
    assert set(_KEYWORD_PROMPTS) == {"image", "video", "chat", "ecommerce", "ppt", "image_edit"}
    for scene, prompt in _KEYWORD_PROMPTS.items():
        r = _embed_classify_direct(prompt)
        assert r is not None, f"{scene} 关键词 prompt {prompt!r} 未命中 embedding"
        assert r.scene == scene, f"{prompt!r} 应命中 {scene}，实际 {r.scene}"
        assert r.confidence >= threshold, f"{prompt!r} confidence {r.confidence} < 阈值 {threshold}"
        assert r.matched_rule == f"embed:{scene}"
        assert r.llm_used is False


@pytest.mark.asyncio
async def test_classify_intent_keyword_prompt_hits_scene():
    """classify_intent 全链路：含关键词且规则不命中的 prompt 走 embedding 多原型返回对应 scene。"""
    from api.agent.intent import classify_intent

    # 规则不命中（见 _KEYWORD_PROMPTS 注释），embedding 多原型命中 → 不走 LLM
    r = await classify_intent("我想买这个商品")
    assert r.scene == "ecommerce"
    assert r.confidence >= 0.55
    assert r.llm_used is False


@pytest.mark.asyncio
async def test_fuzzy_prompt_without_keywords_returns_none():
    """无任何关键词的模糊 prompt 直调 _embed_classify 返回 None（单原型+扩展均未达阈值）。"""
    for prompt in ("1+1等于几", "随便给我点东西", "告诉我明天天气"):
        assert _embed_classify_direct(prompt) is None, f"{prompt!r} 不应命中 embedding"


@pytest.mark.asyncio
async def test_fuzzy_prompt_falls_back_to_llm():
    """无关键词模糊 prompt 经 classify_intent 降级 LLM Mock（unknown + llm_used=True）。"""
    from api.agent.intent import classify_intent

    r = await classify_intent("1+1等于几")
    assert r.llm_used is True
    assert r.scene == "unknown"
    assert r.confidence < 0.6


@pytest.mark.asyncio
async def test_disabled_returns_unknown(monkeypatch):
    """IF_AGENT_INTENT_CLASSIFIER=0 → 返回 unknown + confidence=0（零回归）。

    monkeypatch.setenv 后必须 reset_settings()（任务约束）。
    """
    import api.agent.intent as intent_mod
    from api.config import reset_settings

    monkeypatch.setenv("IF_AGENT_INTENT_CLASSIFIER", "0")
    reset_settings()
    try:
        monkeypatch.setattr(intent_mod, "INTENT_CLASSIFIER_ENABLED", False)
        r = await intent_mod.classify_intent("我想要一张好看的图片")
        assert r.scene == "unknown"
        assert r.confidence == 0.0
        assert r.matched_rule == "disabled"
    finally:
        reset_settings()


@pytest.mark.asyncio
async def test_keyword_weighting_raises_confidence_over_threshold():
    """关键词加权：含"图片"的 prompt 靠 +0.15 加权命中 image（0.587 >= 0.55）。

    对照组：去掉关键词的同构 prompt 不加权 → 不达阈值 → None（阈值不被降级）。
    """
    # 含关键词 → 加权命中
    r = _embed_classify_direct("我想要一张好看的图片")
    assert r is not None
    assert r.scene == "image"
    assert r.confidence >= 0.55

    # 无关键词同构 prompt → 未加权、不达阈值 → None（加权未把阈值降级）
    assert _embed_classify_direct("我想要一个好看的东西") is None


@pytest.mark.asyncio
async def test_chat_generic_keyword_does_not_steal_image_prompt():
    """'画一只猫' 不含 chat 关键词（回复/写/聊天）→ 不被 chat 加权误吃，仍走规则 image。"""
    from api.agent.intent import classify_intent

    r = await classify_intent("画一只猫")
    assert r.scene == "image"
    assert r.matched_rule != "disabled"
    # 规则已命中（'画一只'）→ 优先规则，权重逻辑不介入
    assert r.confidence >= 0.6


@pytest.mark.asyncio
async def test_all_prototypes_miss_returns_none(monkeypatch):
    """单原型 + 扩展原型全失：_EMBED_PROTO_EXTRAS 置空 + 模糊 prompt → _embed_classify 返回 None。

    同时验证扩展原型缺失/异常不崩主链路（降级 None，非抛异常）。
    """
    import api.agent.intent as intent_mod

    monkeypatch.setattr(intent_mod, "_EMBED_PROTO_EXTRAS", {})
    # 单原型（_EMBED_PROTO_B64 5 键保持）+ 空扩展 → 模糊 prompt 全部未达阈值
    assert intent_mod._embed_classify("1+1等于几") is None
    assert intent_mod._embed_classify("随便给我点东西") is None


@pytest.mark.asyncio
async def test_rule_priority_preserved_when_embedding_active():
    """规则已命中仍优先（v14 语义）：embedding 多原型启用下规则 prompt 仍走规则路径。"""
    from api.agent.intent import classify_intent

    # 规则正则 image 命中 → 直接返回规则结果（不走 embedding / LLM）
    r = await classify_intent("帮我画一张猫的图")
    assert r.scene == "image"
    assert r.llm_used is False

    # 电商规则优先（v14 已验证：'画一个电商主图'→ecommerce 规则优先）
    r2 = await classify_intent("画一个电商主图")
    assert r2.scene == "ecommerce"
    assert r2.llm_used is False


@pytest.mark.asyncio
async def test_proto_extras_have_2_to_4_keywords():
    """_EMBED_PROTO_EXTRAS 契约：6 场景每 scene 补充 2-4 个非空中文关键词/短语。"""
    from api.agent.intent import _EMBED_PROTO_EXTRAS

    assert set(_EMBED_PROTO_EXTRAS) == {"image", "video", "chat", "ecommerce", "ppt", "image_edit"}
    for scene, keywords in _EMBED_PROTO_EXTRAS.items():
        assert 2 <= len(keywords) <= 4, f"{scene} 关键词数应 2-4，实际 {len(keywords)}"
        assert all(isinstance(k, str) and k.strip() for k in keywords), f"{scene} 含空关键词"
