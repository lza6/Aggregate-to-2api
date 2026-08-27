"""mail_extract（AI 兜底邮件验证码/链接提取）单元测试。

覆盖：
- 正则快路径（验证码 6 位 / verify-email 链接）行为不变；
- AI 兜底仅在正则未命中且开启时触发；
- 默认（未开启）不调用 LLM；
- LLM 返回合法 JSON / 纯文本 / 失败时分别处理；
- 失败严格返回 None，不抛异常、不阻塞。
"""
import asyncio
import os

os.environ.setdefault("IF_MAIL_AI_EXTRACT", "0")

from api import mail_extract as me  # noqa: E402


# ── 正则快路径（行为与历史一致）─────────────────────
class TestRegexFastPath:
    def test_code_regex(self):
        assert me._regex_code({"bodyPreview": "验证码 123456 有效"}) == "123456"

    def test_link_regex(self):
        mail = {"bodyHtml": '<a href="https://nanobanana-pro.com/api/auth/verify-email?token=abc&amp;c=1">确认</a>'}
        assert me._regex_verify_link(mail) == (
            "https://nanobanana-pro.com/api/auth/verify-email?token=abc"
        )

    def test_no_mail(self):
        assert me._regex_code(None) is None
        assert me._regex_verify_link(None) is None


# ── 默认未开启 → 不调用 LLM ────────────────────────
class TestDisabledByDefault:
    def test_ai_flag_default_false(self):
        assert me._ai_enabled() is False

    def test_ai_disabled_returns_none_without_calling(self, monkeypatch):
        called = {"n": 0}

        async def fake_chat(model, messages):
            called["n"] += 1
            return {"text": '{"code":"654321"}'}

        async def _run():
            r = await me.extract_code(
                {"bodyPreview": "请验证"}, ai=False, chat_fn=fake_chat, model="m"
            )
            return r

        r = asyncio.run(_run())
        assert r is None
        assert called["n"] == 0, "未开启时不应调用 LLM"


# ── AI 兜底：正则未命中时触发 ──────────────────────
class TestAIFallback:
    def test_ai_code_json(self):
        async def fake_chat(model, messages):
            return {"text": '```json\n{"code":"654321"}\n```'}

        async def _run():
            return await me.extract_code(
                {"bodyPreview": "请确认您的邮箱"},
                ai=True, chat_fn=fake_chat, model="m",
            )

        assert asyncio.run(_run()) == "654321"

    def test_ai_link_plaintext(self):
        async def fake_chat(model, messages):
            return {"text": "链接是 https://nanobanana-pro.com/api/auth/verify-email?token=xyz&cb=1"}

        async def _run():
            return await me.extract_verify_link(
                {"bodyHtml": "点击完成验证"},
                ai=True, chat_fn=fake_chat, model="m",
            )

        assert asyncio.run(_run()) == (
            "https://nanobanana-pro.com/api/auth/verify-email?token=xyz&cb=1"
        )

    def test_regex_still_wins_when_present(self):
        async def fake_chat(model, messages):
            return {"text": '{"code":"999999"}'}

        async def _run():
            return await me.extract_code(
                {"bodyPreview": "验证码 112233"}, ai=True, chat_fn=fake_chat, model="m",
            )

        assert asyncio.run(_run()) == "112233"

    def test_ai_failure_returns_none(self):
        async def fake_chat(model, messages):
            raise RuntimeError("上游超时")

        async def _run():
            return await me.extract_code(
                {"bodyPreview": "请验证"}, ai=True, chat_fn=fake_chat, model="m",
            )

        assert asyncio.run(_run()) is None

    def test_ai_empty_json_returns_none(self):
        async def fake_chat(model, messages):
            return {"text": '{"code":null}'}

        async def _run():
            return await me.extract_code(
                {"bodyPreview": "请验证"}, ai=True, chat_fn=fake_chat, model="m",
            )

        assert asyncio.run(_run()) is None


# ── JSON 解析容错 ─────────────────────────────────
class TestParseAIJson:
    def test_markdown_fence(self):
        assert me._parse_ai_json('```json\n{"a":1}\n```') == {"a": 1}

    def test_plain_json(self):
        assert me._parse_ai_json('{"a":1}') == {"a": 1}

    def test_embedded_brace(self):
        assert me._parse_ai_json('结果是 {"code":"12"} 这样') == {"code": "12"}

    def test_garbage(self):
        assert me._parse_ai_json("没有内容") is None
