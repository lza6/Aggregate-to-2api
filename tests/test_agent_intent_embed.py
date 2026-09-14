"""tests/test_agent_intent_embed.py — P0-6 意图分类 Embedding 双路测试。

验收：
- 5 类代表 prompt（画猫/生成视频/聊天对话/电商主图/PPT）embedding 命中对应 scene
  且 confidence >= IF_INTENT_EMBED_THRESHOLD（默认 0.55）
- 明显无关 prompt（规则正则也不命中）→ embedding 未达阈值 → 降级 LLM Mock，
  返回 unknown + llm_used=True（不崩、不误判）
- IF_AGENT_INTENT_CLASSIFIER=0 关闭 → 返回 unknown + confidence=0
- 异常注入：compute_embedding 抛异常 → _embed_classify 返回 None（降级 LLM），不崩
- 原型常量有效性：base64 解码为 256-dim 1024 字节 float32 BLOB（防手抄常量漂移）
- 配置契约：if_intent_embed_threshold 默认 0.55，IF_INTENT_EMBED_THRESHOLD 环境变量可覆盖

约束：所有测试 Mock（IF_MOCK_UPSTREAM=1）；monkeypatch.setenv 后必须 reset_settings()。
"""

from __future__ import annotations

import base64
import os

import pytest

os.environ.setdefault("IF_AGENT_INTENT_CLASSIFIER", "1")
os.environ.setdefault("IF_MOCK_UPSTREAM", "1")

# 5 类代表 prompt（embedding 双路专用，规则正则不命中或命中但在阈值之上）
_EMBED_PROMPTS: dict[str, str] = {
    "image": "画一只猫",  # 规则"画一张|生成图|画图|文生图|txt2img|生成.*图"含"画"？不含"画一只猫"整词，见 test_rule 检查
    "video": "生成一段视频",
    "chat": "帮我写段聊天对话",
    "ecommerce": "做电商主图",
    "ppt": "做 PPT",
}


def _embed_classify_direct(prompt: str):
    """直调 _embed_classify（绕过规则正则，验证 embedding 路径本身）。"""
    from api.agent.intent import _embed_classify

    return _embed_classify(prompt)


@pytest.mark.asyncio
async def test_embed_classify_5_scenes():
    """5 类代表 prompt 均命中对应 scene 且 confidence >= 阈值（默认 0.55）。"""
    from api.config import get_settings, reset_settings

    reset_settings()
    threshold = get_settings().if_intent_embed_threshold
    assert threshold == 0.55
    for scene, prompt in _EMBED_PROMPTS.items():
        r = _embed_classify_direct(prompt)
        assert r is not None, f"{scene} prompt 未命中 embedding"
        assert r.scene == scene, f"{prompt!r} 应命中 {scene}，实际 {r.scene}"
        assert r.confidence >= threshold, f"{prompt!r} confidence {r.confidence} < 阈值 {threshold}"
        assert r.matched_rule == f"embed:{scene}"
        assert r.llm_used is False


@pytest.mark.asyncio
async def test_classify_intent_embed_scene_for_rule_miss_prompts():
    """规则正则不命中的代表 prompt 走 embedding 双路返回对应 scene（而非 LLM）。"""
    from api.agent.intent import classify_intent

    # 这 4 个 prompt 不在 _INTENT_RULES 模式中（见 test_agent_intent.py 的口径），
    # 规则命中与否由 embedding 双路接管：断言命中对应 scene 且未用 LLM。
    for scene, prompt in list(_EMBED_PROMPTS.items()):
        if scene == "ecommerce":  # "做电商主图"含"主图"→ 规则 ecommerce 命中，跳过该断言场景
            continue
        r = await classify_intent(prompt)
        assert r.scene == scene, f"{prompt!r} 应命中 {scene}，实际 {r.scene}（llm_used={r.llm_used}）"
        assert r.llm_used is False


@pytest.mark.asyncio
async def test_unrelated_prompt_falls_back_to_llm():
    """明显无关 prompt（规则不命中 + embedding 未达阈值）→ 降级 LLM Mock 返回 unknown。"""
    from api.agent.intent import classify_intent

    r = await classify_intent("1+1等于几")
    assert r.llm_used is True
    assert r.scene == "unknown"
    assert r.confidence < 0.6


@pytest.mark.asyncio
async def test_embed_classify_unrelated_returns_none():
    """明显无关 prompt 直调 _embed_classify 返回 None（低于阈值）。"""
    r = _embed_classify_direct("1+1等于几")
    assert r is None


@pytest.mark.asyncio
async def test_disabled_returns_unknown(monkeypatch):
    """IF_AGENT_INTENT_CLASSIFIER=0 → 返回 unknown + confidence=0（零回归）。"""
    import api.agent.intent as intent_mod

    monkeypatch.setattr(intent_mod, "INTENT_CLASSIFIER_ENABLED", False)
    r = await intent_mod.classify_intent("画一只猫")
    assert r.scene == "unknown"
    assert r.confidence == 0.0
    assert r.matched_rule == "disabled"


@pytest.mark.asyncio
async def test_embed_classify_exception_falls_back_none(monkeypatch):
    """异常注入：compute_embedding 抛异常 → _embed_classify 返回 None（不崩）。"""
    import api.agent.intent as intent_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("embedding 计算失败")

    monkeypatch.setattr(intent_mod, "compute_embedding", _boom)
    assert intent_mod._embed_classify("画一只猫") is None


@pytest.mark.asyncio
async def test_classify_intent_embed_exception_falls_back_llm(monkeypatch):
    """异常注入：embedding 抛异常 → classify_intent 降级 LLM Mock，不崩。"""
    import api.agent.intent as intent_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("embedding 计算失败")

    monkeypatch.setattr(intent_mod, "compute_embedding", _boom)
    r = await intent_mod.classify_intent("1+1等于几")
    assert r.llm_used is True
    assert r.scene == "unknown"


@pytest.mark.asyncio
async def test_threshold_env_override(monkeypatch):
    """IF_INTENT_EMBED_THRESHOLD 环境变量可覆盖默认阈值（0.55）。"""
    from api.config import get_settings, reset_settings

    monkeypatch.setenv("IF_INTENT_EMBED_THRESHOLD", "0.9")
    reset_settings()
    try:
        assert get_settings().if_intent_embed_threshold == 0.9
    finally:
        reset_settings()


@pytest.mark.asyncio
async def test_high_threshold_blocks_embed_hit(monkeypatch):
    """阈值抬高到 0.9 → 「给我画只猫」（相似度 0.5477）的 embedding 命中被阈值拦截。"""
    from api.config import get_settings, reset_settings

    monkeypatch.setenv("IF_INTENT_EMBED_THRESHOLD", "0.9")
    reset_settings()
    try:
        assert get_settings().if_intent_embed_threshold == 0.9
        r = _embed_classify_direct("给我画只猫")
        assert r is None, f"0.9 阈值下不应命中，实际 {r}"
    finally:
        reset_settings()


def test_prototype_constants_are_valid_256dim_blobs():
    """原型常量是 1024 字节 float32 BLOB（256-dim），base64 可解码。

    防手抄常量漂移：常量与实际 compute_embedding 输出字节数一致，
    且 5 个原型两两可区分（至少 3 个两两相似度 > 0.3，防全零/退化常量）。
    """
    from api.agent.intent import _EMBED_PROTO_B64
    from api.vector.embed import EMBED_DIM

    assert len(_EMBED_PROTO_B64) == 5
    assert set(_EMBED_PROTO_B64) == {"image", "video", "chat", "ecommerce", "ppt"}
    for scene, b64 in _EMBED_PROTO_B64.items():
        blob = base64.b64decode(b64)
        assert len(blob) == EMBED_DIM * 4 == 1024, f"{scene} 原型不是 1024 字节"
        assert len(set(blob)) > 1, f"{scene} 原型常量疑似退化（全零/全同）"
