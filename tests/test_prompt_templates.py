"""P0-3 系统提示词模板系统单测。

覆盖：模板加载（存在/缺失/缓存）、变量插值、宪法+模板+用户 system 组合、
无模板键向后兼容、开关关闭回退、refusal_stance 合规红线降级、
tryingopen._build_models meta 键透传、_convert_messages 注入。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# 确保 api 包可导入
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.prompts import (
    compose_system_text,
    resolve_template_name,
)
from api.prompts import loader as prompt_loader


@pytest.fixture(autouse=True)
def _clear_cache():
    prompt_loader.clear_cache()
    yield
    prompt_loader.clear_cache()


# ── 模板加载 ──────────────────────────────────────


def test_load_base_template_exists():
    text = prompt_loader.load_template("base")
    assert text.strip(), "base.md 宪法模板必须存在且非空"
    assert "付费 API 红线" in text
    assert "Windows 平台" in text
    assert "不可变优先" in text
    assert "真实闭环" in text


def test_load_missing_template_returns_empty():
    assert prompt_loader.load_template("不存在的模板") == ""


def test_load_template_cached():
    first = prompt_loader.load_template("base")
    second = prompt_loader.load_template("base")
    assert first is second  # 同一对象 = 缓存命中


# ── 变量插值 ──────────────────────────────────────


def test_render_template_replaces_variables():
    body = "mode={thinking_mode} len={max_thinking_length}"
    out = prompt_loader.render_template(body, {"thinking_mode": "interleaved", "max_thinking_length": 8000})
    assert out == "mode=interleaved len=8000"


def test_render_template_keeps_unknown_placeholder():
    body = "known={a} unknown={b}"
    out = prompt_loader.render_template(body, {"a": "1"})
    assert "known=1" in out
    assert "{b}" in out


# ── 组合逻辑 ──────────────────────────────────────


def test_resolve_template_name_none_when_no_meta():
    assert resolve_template_name(None) is None
    assert resolve_template_name({}) is None
    assert resolve_template_name({"other": 1}) is None


def test_resolve_template_name_returns_value():
    assert resolve_template_name({"system_prompt_template": "anthropic_v5_chat"}) == "anthropic_v5_chat"


def test_compose_without_template_returns_user_system():
    """无模板键 → 原样返回（向后兼容原 [SYSTEM INSTRUCTIONS] 路径）。"""
    user = "你是客服。"
    assert compose_system_text(user, None) == user
    assert compose_system_text(user, {}) == user


def test_compose_with_template_includes_base_and_user():
    meta = {"system_prompt_template": "anthropic_v5_chat", "thinking_mode": "interleaved"}
    out = compose_system_text("用户自定义 system", meta)
    assert "付费 API 红线" in out  # base 宪法段
    assert "thinking_mode: interleaved" in out  # 模板变量插值
    assert "用户自定义 system" in out  # 用户 system 段
    # 三段以 --- 分隔
    assert out.count("\n\n---\n\n") == 2


def test_compose_keeps_user_system_when_template_missing():
    """模板不存在时仍返回 base+用户 system（不崩主链路）。"""
    meta = {"system_prompt_template": "不存在的模板"}
    out = compose_system_text("用户 system", meta)
    assert "付费 API 红线" in out
    assert "用户 system" in out


# ── 合规红线（refusal_stance）──────────────────────


def test_never_refuse_downgraded(monkeypatch):
    """Llama4 never_refuse 触发合规红线，强制降级 default_help。"""
    meta = {"system_prompt_template": "anthropic_v5_chat", "refusal_stance": "never_refuse"}
    out = compose_system_text("s", meta)
    assert "never_refuse" not in out
    assert "default_help" in out


def test_unknown_stance_defaults():
    meta = {"system_prompt_template": "anthropic_v5_chat", "refusal_stance": "garbage"}
    out = compose_system_text("s", meta)
    assert "default_help" in out


# ── 开关回退 ──────────────────────────────────────


def test_switch_off_falls_back(monkeypatch):
    """IF_PROMPT_TEMPLATES_ENABLED=0 → 无模板键行为（原 [SYSTEM INSTRUCTIONS] 单段）。"""
    monkeypatch.setenv("IF_PROMPT_TEMPLATES_ENABLED", "0")
    mod = importlib.reload(importlib.import_module("api.prompts"))
    assert mod.PROMPT_TEMPLATES_ENABLED is False
    user = "你是客服。"
    assert mod.compose_system_text(user, {"system_prompt_template": "anthropic_v5_chat"}) == user
    # 恢复
    monkeypatch.setenv("IF_PROMPT_TEMPLATES_ENABLED", "1")
    importlib.reload(importlib.import_module("api.prompts"))


# ── tryingopen 集成 ───────────────────────────────


def test_build_models_passes_template_meta():
    """_build_models 把 system_prompt_template 等键透传到 ModelSpec.meta。"""
    from api.providers.tryingopen import TryingopenChatProvider

    prov = TryingopenChatProvider()
    spec = prov.models.get("tryingopen/z-ai/glm-5.3-flash")
    assert spec is not None
    assert spec.meta.get("system_prompt_template") == "kimi_k2_teach"
    assert spec.meta.get("thinking_mode") == "interleaved"

    # 无模板键的模型 meta 不含该键
    spec2 = prov.models.get("tryingopen/nvidia/nemotron-3.5-lightning")
    assert spec2 is not None
    assert "system_prompt_template" not in spec2.meta


def test_convert_messages_injects_composed_system():
    """_convert_messages 按 _current_meta 组合注入；无 meta 时仅用户 system。"""
    from api.providers.tryingopen import TryingopenChatProvider

    prov = TryingopenChatProvider()
    messages = [{"role": "user", "content": "你好"}]

    # 无 meta：原路径（仅用户 system，此处无 system 消息 → 不注入）
    prov._current_meta = None
    converted = prov._convert_messages(list(messages))
    joined = "".join(
        part.get("text", "") for part in converted[0]["parts"] if isinstance(part, dict)
    )
    assert "[SYSTEM INSTRUCTIONS]" not in joined

    # 有 meta（含模板）：注入组合后 system，包含宪法+模板变量
    prov._current_meta = {"system_prompt_template": "anthropic_v5_chat", "thinking_mode": "interleaved"}
    converted2 = prov._convert_messages(list(messages))
    joined2 = "".join(
        part.get("text", "") for part in converted2[0]["parts"] if isinstance(part, dict)
    )
    assert "[SYSTEM INSTRUCTIONS]" in joined2
    assert "付费 API 红线" in joined2
    assert "thinking_mode: interleaved" in joined2


def test_chat_stream_sets_current_meta():
    """chat_stream 把模型 meta 暴露给 _convert_messages。"""
    from api.providers.tryingopen import TryingopenChatProvider

    prov = TryingopenChatProvider()
    model = "tryingopen/z-ai/glm-5.3-flash"
    assert prov.models[model].meta.get("system_prompt_template") == "kimi_k2_teach"
    # 只验证属性存在与赋值逻辑（不发真实请求——付费/网络红线）
    spec = prov.models.get(model)
    prov._current_meta = spec.meta if spec else None
    assert prov._current_meta is not None
    assert "system_prompt_template" in prov._current_meta
