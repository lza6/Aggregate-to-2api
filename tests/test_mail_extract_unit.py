"""api/mail_extract.py 单元测试（P0-2 覆盖率补强）。

覆盖：正则快路径（code/link）、_ai_extract_kind（code/link 各分支 + LLM 异常 + JSON 解析容错）、
_parse_ai_json（markdown/裸 JSON/外层花括号兜底/非法）、_ai_enabled、extract_code/extract_verify_link
（正则命中短路/AI 默认关闭/AI 开启+自定义 chat_fn/默认通道不可用降级）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import api.mail_extract as me


# ── _mail_blob / 正则快路径 ──────────────────────────────────


def test_mail_blob_null():
    assert me._mail_blob(None) == ""


def test_mail_blob_prefer_html():
    mail = {"bodyHtml": "<b>x</b>", "bodyPreview": "prev", "subject": "sub"}
    assert "<b>x</b>" in me._mail_blob(mail, prefer_html=True)
    assert "prev" in me._mail_blob(mail, prefer_html=False)


def test_regex_code_hit():
    assert me._regex_code({"bodyPreview": "your code is 123456 please"}) == "123456"


def test_regex_code_miss():
    assert me._regex_code({"bodyPreview": "no code here"}) is None


def test_regex_verify_link_hit_and_amp_decoded():
    mail = {"bodyHtml": 'click <a href="https://x.com/api/auth/verify-email?token=abc&amp;u=1">verify</a>'}
    link = me._regex_verify_link(mail)
    assert link is not None
    # 正则匹配到 ?token=abc 截止（&amp;u=1 在非贪婪边界外），amp 被解码
    assert link == "https://x.com/api/auth/verify-email?token=abc"


def test_regex_verify_link_miss():
    assert me._regex_verify_link({"bodyHtml": "no link"}) is None


# ── _parse_ai_json ───────────────────────────────────────────


def test_parse_plain_json():
    assert me._parse_ai_json('{"code":"123456"}') == {"code": "123456"}


def test_parse_markdown_block():
    assert me._parse_ai_json('```json\n{"link":"https://x"}\n```') == {"link": "https://x"}


def test_parse_outer_braces_in_prose():
    assert me._parse_ai_json('result is {"code":"42"} done') == {"code": "42"}


def test_parse_empty_returns_none():
    assert me._parse_ai_json("") is None
    assert me._parse_ai_json("no json here") is None


def test_parse_non_dict_returns_none():
    assert me._parse_ai_json("[1,2,3]") is None


# ── _ai_enabled ──────────────────────────────────────────────


def test_ai_enabled_config_true(monkeypatch):
    monkeypatch.setattr(me.config, "IF_MAIL_AI_EXTRACT", True)
    assert me._ai_enabled() is True


def test_ai_enabled_config_false(monkeypatch):
    monkeypatch.setattr(me.config, "IF_MAIL_AI_EXTRACT", False)
    assert me._ai_enabled() is False


def test_ai_enabled_attr_missing_returns_false(monkeypatch):
    monkeypatch.delattr(me.config, "IF_MAIL_AI_EXTRACT", raising=False)
    assert me._ai_enabled() is False


# ── _ai_extract_kind ────────────────────────────────────────


@pytest.mark.asyncio
async def test_ai_extract_code_success():
    chat_fn = AsyncMock(return_value={"text": '```json\n{"code":"999000"}\n```'})
    r = await me._ai_extract_kind({"bodyPreview": "x"}, "code", chat_fn, "m")
    assert r == "999000"
    chat_fn.assert_awaited_once()


@pytest.mark.asyncio
async def test_ai_extract_link_success():
    chat_fn = AsyncMock(return_value={"text": '{"link":"https://verify.example/confirm?token=z"}'})
    r = await me._ai_extract_kind({"bodyPreview": "x"}, "link", chat_fn, "m")
    assert r is not None and r.startswith("https://verify.example/confirm")


@pytest.mark.asyncio
async def test_ai_extract_link_from_text_fallback():
    """JSON 解析失败但 LLM 文本含 https 链接 → 直接提取。"""
    chat_fn = AsyncMock(return_value={"text": "see https://example.com/confirm?t=1"})
    r = await me._ai_extract_kind({"bodyPreview": "x"}, "link", chat_fn, "m")
    assert r == "https://example.com/confirm?t=1"


@pytest.mark.asyncio
async def test_ai_extract_code_value_non_string_returns_none():
    chat_fn = AsyncMock(return_value={"text": '{"code": null}'})
    assert await me._ai_extract_kind({"bodyPreview": "x"}, "code", chat_fn, "m") is None


@pytest.mark.asyncio
async def test_ai_extract_code_empty_string_returns_none():
    chat_fn = AsyncMock(return_value={"text": '{"code": "   "}'})
    assert await me._ai_extract_kind({"bodyPreview": "x"}, "code", chat_fn, "m") is None


@pytest.mark.asyncio
async def test_ai_extract_chat_exception_returns_none():
    chat_fn = AsyncMock(side_effect=TimeoutError("slow"))
    assert await me._ai_extract_kind({"bodyPreview": "x"}, "code", chat_fn, "m") is None


@pytest.mark.asyncio
async def test_ai_extract_null_mail_returns_none():
    assert await me._ai_extract_kind(None, "code", AsyncMock(), "m") is None


@pytest.mark.asyncio
async def test_ai_extract_result_not_dict():
    chat_fn = AsyncMock(return_value="plain string")
    # text 取 str(result)；_parse_ai_json 对非 json 文本返回 None → code None
    assert await me._ai_extract_kind({"bodyPreview": "x"}, "code", chat_fn, "m") is None


# ── extract_code / extract_verify_link 集成分支 ──────────────


@pytest.mark.asyncio
async def test_extract_code_regex_short_circuits(monkeypatch):
    """正则命中 → 不走 AI。"""
    ai_called = AsyncMock(return_value="should-not-reach")
    r = await me.extract_code({"bodyPreview": "code: 654321"}, ai=True, chat_fn=ai_called, model="m")
    assert r == "654321"
    ai_called.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_code_ai_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(me.config, "IF_MAIL_AI_EXTRACT", False)
    assert await me.extract_code({"bodyPreview": "no code"}) is None


@pytest.mark.asyncio
async def test_extract_code_ai_enabled_custom_chat_fn():
    chat_fn = AsyncMock(return_value={"text": '{"code":"111222"}'})
    r = await me.extract_code({"bodyPreview": "no code"}, ai=True, chat_fn=chat_fn, model="m")
    assert r == "111222"


@pytest.mark.asyncio
async def test_extract_code_ai_default_channel_unavailable(monkeypatch):
    """ai=None 且 IF_MAIL_AI_EXTRACT=True，但 _default_chat_fn 返回 None → 降级 None。"""
    monkeypatch.setattr(me.config, "IF_MAIL_AI_EXTRACT", True)
    monkeypatch.setattr(me, "_default_chat_fn", lambda: None)
    assert await me.extract_code({"bodyPreview": "no code"}) is None


@pytest.mark.asyncio
async def test_extract_verify_link_regex_short_circuits():
    mail = {"bodyHtml": "https://x/api/auth/verify-email?token=t"}
    r = await me.extract_verify_link(mail, ai=True, chat_fn=AsyncMock(), model="m")
    assert r is not None and "token=t" in r


@pytest.mark.asyncio
async def test_extract_verify_link_ai_custom():
    chat_fn = AsyncMock(return_value={"text": '{"link":"https://ok/verify?token=y"}'})
    r = await me.extract_verify_link({"bodyHtml": "no link"}, ai=True, chat_fn=chat_fn, model="m")
    assert r is not None and "token=y" in r


# ── _default_chat_fn ─────────────────────────────────────────


def _get_registry_module():
    """用 importlib 取子模块（避免包 __init__ 把 registry 实例覆盖子模块同名）。"""
    import importlib

    return importlib.import_module("api.providers.registry")


def test_default_chat_fn_no_provider(monkeypatch):
    """registry 无 tryingopen provider → 返回 None（不抛）。"""
    reg = _get_registry_module()

    class FakeRegistry:
        chat_providers = {}

    monkeypatch.setattr(reg, "bootstrap", lambda: None)
    monkeypatch.setattr(reg, "registry", FakeRegistry())
    assert me._default_chat_fn() is None


def test_default_chat_fn_provider_with_models(monkeypatch):
    reg = _get_registry_module()

    class FakeProvider:
        def all_models(self):
            from api.providers.base import ModelSpec

            return [ModelSpec(id="tryingopen/m1", provider="tryingopen", upstream_model="m1", capabilities=("chat",))]

        async def chat_collect(self, *a):
            return {"text": "x"}

    class FakeRegistry:
        chat_providers = {"tryingopen": FakeProvider()}

    monkeypatch.setattr(reg, "bootstrap", lambda: None)
    monkeypatch.setattr(reg, "registry", FakeRegistry())
    chat_fn, model = me._default_chat_fn()
    assert chat_fn is not None and model == "tryingopen/m1"


def test_default_chat_fn_provider_without_models(monkeypatch):
    reg = _get_registry_module()

    class FakeProvider:
        def all_models(self):
            return []

    class FakeRegistry:
        chat_providers = {"tryingopen": FakeProvider()}

    monkeypatch.setattr(reg, "bootstrap", lambda: None)
    monkeypatch.setattr(reg, "registry", FakeRegistry())
    assert me._default_chat_fn() is None
