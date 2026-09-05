"""tests/test_agent_critic.py — P1-A7 独立终检 Agent 测试。

验收：
- Mock 路径：review_generation 不调 LLM，基于规则评分
- 重试过多扣分（retry_count>=2）
- 超时扣分（duration_ms>30000）
- prompt 过短扣分（len<5）
- 开关关闭：pass=True + score=1.0（零回归）
- LLM Mock（IF_MOCK_UPSTREAM=1）：不崩主链路
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("IF_CRITIC_AGENT_ENABLED", "1")
os.environ.setdefault("IF_MOCK_UPSTREAM", "1")


@pytest.mark.asyncio
async def test_critic_mock_pass():
    """Mock 路径：正常生成 pass=True。"""
    from api.agent.critic import review_generation

    c = await review_generation("一只可爱的猫咪", scene="image", provider="imagefree", duration_ms=5000, retry_count=0)
    assert c.pass_check is True
    assert c.score >= 0.6
    assert c.recommendation == "accept"
    assert c.llm_used is False


@pytest.mark.asyncio
async def test_critic_mock_retry_penalty():
    """重试 >=2 次扣分。"""
    from api.agent.critic import review_generation

    c = await review_generation("一只猫", scene="image", provider="imagefree", duration_ms=1000, retry_count=3)
    assert "retry_count=3" in c.issues
    assert c.score < 1.0


@pytest.mark.asyncio
async def test_critic_mock_slow_duration_penalty():
    """超时扣分（duration_ms>30000）。"""
    from api.agent.critic import review_generation

    c = await review_generation("一只猫", scene="image", provider="imagefree", duration_ms=50000, retry_count=0)
    assert any("slow_duration" in i for i in c.issues)
    assert c.score < 1.0


@pytest.mark.asyncio
async def test_critic_mock_short_prompt_penalty():
    """prompt 过短扣分（len<5）。"""
    from api.agent.critic import review_generation

    c = await review_generation("猫", scene="image", provider="imagefree", duration_ms=1000, retry_count=0)
    assert any("prompt_too_short" in i for i in c.issues)


@pytest.mark.asyncio
async def test_critic_disabled_returns_pass(monkeypatch):
    """IF_CRITIC_AGENT_ENABLED=0 → pass=True + score=1.0（零回归）。"""
    import api.agent.critic as critic_mod

    monkeypatch.setattr(critic_mod, "CRITIC_AGENT_ENABLED", False)
    c = await critic_mod.review_generation("test", scene="image", provider="imagefree")
    assert c.pass_check is True
    assert c.score == 1.0
    assert c.recommendation == "accept"


@pytest.mark.asyncio
async def test_critic_result_immutable():
    """CriticResult 是 frozen dataclass（不可变）。"""
    from api.agent.critic import CriticResult

    r = CriticResult(pass_check=True, score=0.9)
    with pytest.raises((AttributeError, Exception)):
        r.pass_check = False  # type: ignore[misc]
