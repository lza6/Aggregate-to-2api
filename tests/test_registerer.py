"""registerer（自动注册器）单元测试。

覆盖：注册器注册表结构、nanobanana MOCK 注册路径、
nanobanana 签到循环（含 Server Action 领取响应解析 L1/L5 修复）、
邮箱验证码/验证链接提取逻辑。
"""
import base64
import json
import os

import pytest

os.environ.setdefault("IF_MOCK_REGISTER", "1")
os.environ.setdefault("IF_ACCOUNT_AUTO", "0")

from api.registerer import (  # noqa: E402
    NanobananaRegisterer,
    _extract_code,
    _extract_verify_link,
    build_registerers,
)


# ── 注册表结构 ─────────────────────────────────────
class TestBuildRegisterers:
    def test_returns_nanobanana(self):
        regs = build_registerers()
        assert set(regs) == {"nanobanana"}
        assert isinstance(regs["nanobanana"], NanobananaRegisterer)

    def test_registerers_expose_register_checkin(self):
        for r in build_registerers().values():
            assert callable(r.register_one)
            assert callable(r.checkin)


# ── MOCK 注册路径（cash 时）─────────────────────────
class TestMockRegister:
    @pytest.mark.asyncio
    async def test_nanobanana_mock_register(self, monkeypatch):
        monkeypatch.setattr("api.registerer.MOCK_REGISTER", True)
        r = NanobananaRegisterer()
        acc = await r.register_one()
        assert acc is not None
        assert acc["email"].startswith("mocknb")
        assert acc["cookie"] == "mock-session"
        assert acc["credits"] == 4
        r.client.close()

    @pytest.mark.asyncio
    async def test_nanobanana_mock_checkin_increments(self, monkeypatch):
        monkeypatch.setattr("api.registerer.MOCK_REGISTER", True)
        r = NanobananaRegisterer()
        res = await r.checkin({"credits": 10})
        assert res == 14
        res = await r.checkin({})
        assert res == 4  # 无 credits 字段 → 0 + 4
        r.client.close()


# ── 邮箱提取逻辑 ───────────────────────────────────
class TestExtractCode:
    def test_extracts_six_digit_code(self):
        mail = {"bodyPreview": "您的验证码是 123456，5 分钟内有效。"}
        assert _extract_code(mail) == "123456"

    def test_no_mail_returns_none(self):
        assert _extract_code(None) is None

    def test_no_code_returns_none(self):
        assert _extract_code({"bodyPreview": "欢迎使用", "subject": "注册通知"}) is None

    def test_code_extracted_from_html_body(self):
        mail = {"bodyHtml": "<h1>code</h1><p>987654</p>"}
        assert _extract_code(mail) == "987654"


class TestExtractVerifyLink:
    def test_extracts_verify_link(self):
        mail = {"bodyHtml": '<a href="https://nanobanana-pro.com/api/auth/verify-email?token=abc123&amp;callback=1">确认</a>'}
        link = _extract_verify_link(mail)
        assert link is not None
        assert link.startswith("https://nanobanana-pro.com/api/auth/verify-email")
        assert link == "https://nanobanana-pro.com/api/auth/verify-email?token=abc123"  # token 即中断

    def test_no_link_returns_none(self):
        assert _extract_verify_link({"bodyHtml": "no link"}) is None
        assert _extract_verify_link(None) is None


# ── 代理轮换（_ensure_client 重建）──────────────────
class TestEnsureClient:
    def test_proxy_injection_rebuilds_client(self, monkeypatch):
        r = NanobananaRegisterer()
        old = r.client
        r._ensure_client("")
        assert r.client is old  # 代理未变 → 复用
        r.proxy = "http://127.0.0.1:99999"
        r._ensure_client("")
        assert r.client is not old  # 代理变化 → 重建
        r.client.close()

    def test_proxy_priority(self, monkeypatch):
        r = NanobananaRegisterer()
        monkeypatch.setattr(r, "proxy", "http://injected:8000")
        r._current_proxy = None  # 强制重建
        r._ensure_client("e@x.com")
        assert r._current_proxy == "http://injected:8000"  # 显式注入优先
        r.proxy = None
        r._current_proxy = None
        r._ensure_client("e@x.com")
        # 无显式注入时走 config.PROXY（kookeey 已移除，不再 fallback 到 kookeey）
        from api import config
        assert r._current_proxy == config.PROXY
        r.client.close()


# ── _ensure_client 的 mock 客户端默认创建（仅构造路径）──
def test_clients_are_httpx(monkeypatch):
    monkeypatch.setattr("api.registerer.config.PROXY", None)
    r = NanobananaRegisterer()
    assert hasattr(r.client, "post")
    r.client.close()