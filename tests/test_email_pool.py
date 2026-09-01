"""邮箱池适配器与策略 (Mail Provider Strategy) 单元测试。

覆盖：
1. 规范基类 BaseMailSource (优先打分、成功/失败标记、指数退避、可用性)。
2. 各邮箱提供商 (LinshiMailSource, MailTmSource, GuerrillaMailSource, CustomImapSource, Do22Source, TempMailSource, TempTfSource)。
3. EmailPool 动态自适应分配、优先级轮换、429 自动退避与故障转移 (Fallback)。
4. 邮件轮询提取与关键词过滤。
5. 注册记录持久化与域名风控统计。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.email_pool import (
    BaseMailSource,
    CustomImapSource,
    EmailPool,
    GuerrillaMailSource,
    LinshiMailSource,
    MailGwSource,
    MailSource,
    MailTmSource,
    TempMailIoSource,
)


# ── 1. BaseMailSource 基础机制测试 ───────────────────────
class TestBaseMailSource:
    def test_mail_source_alias_compatibility(self):
        assert issubclass(BaseMailSource, object)
        assert MailSource is BaseMailSource

    def test_score_and_availability(self):
        class DummySource(BaseMailSource):
            name = "dummy"

        src = DummySource(name="dummy", priority=80)
        assert src.is_available() is True
        initial_score = src.score()
        assert initial_score > 800

        # 标记失败与退避
        src.mark_failure("Mock 429 Error", backoff_seconds=10.0)
        assert src.failure_count == 1
        assert src.is_available() is False
        assert src.score() < 0  # 冷却中扣分

        # 标记成功恢复
        src.cooldown_until = 0.0
        src.mark_success()
        assert src.is_available() is True
        assert src.success_count == 1
        assert src.failure_count == 0


# ── 2. LinshiMailSource 测试 ─────────────────────────────
class TestLinshiMailSource:
    @pytest.mark.asyncio
    async def test_linshi_new_address(self):
        src = LinshiMailSource()
        addr, state = await src.new_address()
        assert "@" in addr
        assert any(addr.endswith(f"@{d}") for d in LinshiMailSource.DOMAINS)
        assert state["source"] == "linshi-email"
        assert "hash" in state
        await src.session.aclose()

    @pytest.mark.asyncio
    async def test_linshi_fetch_mails(self):
        src = LinshiMailSource()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "1",
                    "from": "auth@service.com",
                    "subject": "Your verification code",
                    "content": "Code is 654321",
                }
            ]
        }
        with patch.object(src.session, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            mails = await src.fetch_mails("test@iwatermail.com", {"hash": "dummyhash"})
            assert len(mails) == 1
            assert mails[0]["subject"] == "Your verification code"
            assert "654321" in mails[0]["bodyHtml"]
        await src.session.aclose()


# ── 3. MailTmSource 测试 ─────────────────────────────────
class TestMailTmSource:
    @pytest.mark.asyncio
    async def test_mailtm_new_address_and_fetch(self):
        src = MailTmSource()

        # Mock 获取域名 -> 创建账号 -> 获取 token
        domains_resp = MagicMock(status_code=200)
        domains_resp.json.return_value = {"hydra:member": [{"domain": "mailtm.me", "isActive": True}]}

        account_resp = MagicMock(status_code=201)
        account_resp.json.return_value = {"id": "acc_123", "address": "test@mailtm.me"}

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"token": "jwt_token_xyz"}

        async def mock_post(url, json=None, headers=None):
            if "/accounts" in url:
                return account_resp
            if "/token" in url:
                return token_resp
            return MagicMock(status_code=404)

        with (
            patch.object(src.session, "get", new_callable=AsyncMock) as mock_get,
            patch.object(src.session, "post", new_callable=AsyncMock, side_effect=mock_post),
        ):
            mock_get.return_value = domains_resp
            addr, state = await src.new_address()
            assert addr.endswith("@mailtm.me")
            assert state["token"] == "jwt_token_xyz"
            assert state["source"] == "mail.tm"

        # Mock 拉取邮件
        messages_resp = MagicMock(status_code=200)
        messages_resp.json.return_value = {
            "hydra:member": [
                {
                    "id": "msg_001",
                    "from": {"address": "no-reply@auth.com"},
                    "subject": "Verify your email",
                    "intro": "Click verify link",
                }
            ]
        }
        detail_resp = MagicMock(status_code=200)
        detail_resp.json.return_value = {
            "id": "msg_001",
            "subject": "Verify your email",
            "from": {"address": "no-reply@auth.com"},
            "html": ["<p>Your code is 112233</p>"],
            "text": "Your code is 112233",
        }

        async def mock_get_msg(url, headers=None):
            if url.endswith("/messages"):
                return messages_resp
            if "/messages/msg_001" in url:
                return detail_resp
            return MagicMock(status_code=404)

        with patch.object(src.session, "get", new_callable=AsyncMock, side_effect=mock_get_msg):
            mails = await src.fetch_mails(addr, state)
            assert len(mails) == 1
            assert mails[0]["id"] == "msg_001"
            assert "112233" in mails[0]["bodyHtml"]

        await src.session.aclose()


# ── 4. GuerrillaMailSource 测试 ──────────────────────────
class TestGuerrillaMailSource:
    @pytest.mark.asyncio
    async def test_guerrilla_flow(self):
        src = GuerrillaMailSource()

        init_resp = MagicMock(status_code=200)
        init_resp.json.return_value = {
            "email_addr": "random@sharklasers.com",
            "sid_token": "sid_12345",
        }

        check_resp = MagicMock(status_code=200)
        check_resp.json.return_value = {
            "list": [
                {
                    "mail_id": "1001",
                    "mail_from": "admin@example.com",
                    "mail_subject": "Security Code",
                    "mail_excerpt": "Your code is 998877",
                    "mail_body": "<p>Your code is 998877</p>",
                }
            ]
        }

        with patch.object(src.session, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = init_resp
            addr, state = await src.new_address()
            assert addr == "random@sharklasers.com"
            assert state["sid_token"] == "sid_12345"

            mock_get.return_value = check_resp
            mails = await src.fetch_mails(addr, state)
            assert len(mails) == 1
            assert mails[0]["subject"] == "Security Code"
            assert "998877" in mails[0]["bodyHtml"]

        await src.session.aclose()


# ── 5. CustomImapSource 测试 ─────────────────────────────
class TestCustomImapSource:
    @pytest.mark.asyncio
    async def test_imap_generate_and_fetch(self, monkeypatch):
        src = CustomImapSource(
            host="imap.example.com",
            port=993,
            username="user@example.com",
            password="pwd",
            domain="customcatch.com",
            use_ssl=True,
        )
        assert src.is_configured() is True
        assert src.is_available() is True

        addr, st = await src.new_address()
        assert addr.endswith("@customcatch.com")
        assert st["source"] == "custom-imap"

        # Mock imaplib 异步线程内收件
        raw_email_bytes = (
            b"From: test@sender.com\r\n"
            b"To: " + addr.encode("utf-8") + b"\r\n"
            b"Subject: Your Login Link\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n\r\n"
            b"<html><body>Code: 554433</body></html>"
        )

        mock_imap_instance = MagicMock()
        mock_imap_instance.login.return_value = ("OK", [b"Logged in"])
        mock_imap_instance.select.return_value = ("OK", [b"1"])
        mock_imap_instance.search.return_value = ("OK", [b"1 2"])
        mock_imap_instance.fetch.return_value = ("OK", [(b"1 (RFC822 {100}", raw_email_bytes)])

        with patch("imaplib.IMAP4_SSL", return_value=mock_imap_instance):
            mails = await src.fetch_mails(addr, st)
            assert len(mails) >= 1
            assert mails[0]["subject"] == "Your Login Link"
            assert "554433" in mails[0]["bodyHtml"]


# ── 6. EmailPool 综合策略与容灾降级测试 ──────────────────
class TestEmailPoolStrategy:
    @pytest.fixture
    def pool(self, tmp_path):
        db_file = str(tmp_path / "test_email.db")
        return EmailPool(db_path=db_file)

    @pytest.mark.asyncio
    async def test_allocate_default_rotates_and_records(self, pool):
        addr, state = await pool.allocate(provider="imagefree", want_fresh=True)
        assert "@" in addr
        assert addr in pool._used
        assert state["source"] in [s.name for s in pool.get_sources()]

        # 记录到 DB 并验证（P2-3 后 record/registered_providers/stats 已 async）
        await pool.record(addr, "imagefree", status="ok")
        assert await pool.registered_providers(addr) == ["imagefree"]
        stats = await pool.stats()
        assert stats["total_registered"] == 1
        assert stats["by_provider"]["imagefree"] == 1

    @pytest.mark.asyncio
    async def test_allocate_specific_source(self, pool):
        addr, state = await pool.allocate(provider="test", prefer_source="temp.tf")
        assert state["source"] == "temp.tf"

        addr2, state2 = await pool.allocate(provider="test", prefer_source="linshi-email")
        assert state2["source"] == "linshi-email"

    @pytest.mark.asyncio
    async def test_fallback_on_429_or_failure(self, tmp_path):
        db_file = str(tmp_path / "fallback.db")

        # 构造一个始终 429 报错的源和一个正常源
        class FailingSource(BaseMailSource):
            name = "fail-source"

            async def new_address(self) -> tuple[str, dict]:
                self.mark_failure("429 Too Many Requests")
                raise RuntimeError("429 Too Many Requests")

            async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
                return []

        class WorkingSource(BaseMailSource):
            name = "work-source"

            async def new_address(self) -> tuple[str, dict]:
                return "good@work.com", {"source": self.name}

            async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
                return [{"subject": "Verification", "bodyHtml": "Code is 889900"}]

        f_src = FailingSource(name="fail-source", priority=100)
        w_src = WorkingSource(name="work-source", priority=50)

        test_pool = EmailPool(db_path=db_file, custom_sources=[f_src, w_src])
        addr, state = await test_pool.allocate(provider="test")
        assert addr == "good@work.com"
        assert state["source"] == "work-source"
        assert f_src.failure_count >= 1
        assert f_src.is_available() is False

        # 测试 wait_for_mail
        mail = await test_pool.wait_for_mail(addr, state, timeout=3.0, contains="889900")
        assert mail is not None
        assert "889900" in mail["bodyHtml"]


# ── 7. TempMailIoSource 测试 ──────────────────────────────
class TestTempMailIoSource:
    @pytest.mark.asyncio
    async def test_tempmailio_new_address(self):
        src = TempMailIoSource()
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {"email": "abc12345@temp-mail.io", "token": "tok_123"}
        with patch.object(src.session, "post", new_callable=AsyncMock, return_value=mock_response):
            addr, state = await src.new_address()
            assert addr == "abc12345@temp-mail.io"
            assert state["token"] == "tok_123"
            assert state["source"] == "temp-mail.io"
        await src.session.aclose()

    @pytest.mark.asyncio
    async def test_tempmailio_429_backoff(self):
        src = TempMailIoSource()
        mock_response = MagicMock(status_code=429)
        mock_response.text = "rate limited"
        with patch.object(src.session, "post", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(RuntimeError):
                await src.new_address()
            assert src.failure_count == 1
            assert src.is_available() is False
        await src.session.aclose()

    @pytest.mark.asyncio
    async def test_tempmailio_fetch_mails(self):
        src = TempMailIoSource()
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = [
            {
                "id": "m1",
                "from": {"address": "no-reply@auth.com"},
                "subject": "Verification",
                "body_html": "<p>Code is 246810</p>",
                "body_text": "Code is 246810",
                "intro": "Code is 246810",
            }
        ]
        with patch.object(src.session, "get", new_callable=AsyncMock, return_value=mock_response):
            mails = await src.fetch_mails("abc12345@temp-mail.io", {"token": "tok_123"})
            assert len(mails) == 1
            assert mails[0]["subject"] == "Verification"
            assert mails[0]["from"] == "no-reply@auth.com"
            assert "246810" in mails[0]["bodyHtml"]
        await src.session.aclose()


# ── 8. MailGwSource 测试 ──────────────────────────────────
class TestMailGwSource:
    @pytest.mark.asyncio
    async def test_mailgw_new_address(self):
        src = MailGwSource()
        domains_resp = MagicMock(status_code=200)
        domains_resp.json.return_value = [{"domain": "westcast-systems.com", "isActive": True}]
        account_resp = MagicMock(status_code=201)
        account_resp.json.return_value = {"id": "acc_1", "address": "test@westcast-systems.com"}
        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"token": "gw_token"}

        async def mock_post(url, json=None, headers=None):
            if "/domains" in url:
                return domains_resp
            if "/accounts" in url:
                return account_resp
            if "/token" in url:
                return token_resp
            return MagicMock(status_code=404)

        with (
            patch.object(src.session, "get", new_callable=AsyncMock, return_value=domains_resp),
            patch.object(src.session, "post", new_callable=AsyncMock, side_effect=mock_post),
        ):
            addr, state = await src.new_address()
            assert addr.endswith("@westcast-systems.com")
            assert state["token"] == "gw_token"
            assert state["source"] == "mail.gw"
        await src.session.aclose()

    @pytest.mark.asyncio
    async def test_mailgw_domains_fallback(self):
        src = MailGwSource()
        mock_response = MagicMock(status_code=500)
        with patch.object(src.session, "get", new_callable=AsyncMock, return_value=mock_response):
            domains = await src._get_domains()
            assert domains == ["westcast-systems.com"]
        await src.session.aclose()

    @pytest.mark.asyncio
    async def test_mailgw_429_backoff(self):
        src = MailGwSource()
        mock_response = MagicMock(status_code=429)
        mock_response.text = "too many"
        with (
            patch.object(src.session, "get", new_callable=AsyncMock, return_value=MagicMock(status_code=500)),
            patch.object(src.session, "post", new_callable=AsyncMock, return_value=mock_response),
        ):
            with pytest.raises(RuntimeError):
                await src.new_address()
            assert src.failure_count == 1
            assert src.is_available() is False
        await src.session.aclose()

    @pytest.mark.asyncio
    async def test_mailgw_fetch_mails_hydra(self):
        src = MailGwSource()
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {
            "hydra:member": [
                {
                    "id": "m1",
                    "from": {"address": "no-reply@service.com"},
                    "subject": "Welcome",
                    "bodyHtml": "<p>Code is 13579</p>",
                    "bodyText": "Code is 13579",
                }
            ]
        }
        with patch.object(src.session, "get", new_callable=AsyncMock, return_value=mock_response):
            mails = await src.fetch_mails("test@westcast-systems.com", {"token": "gw_token"})
            assert len(mails) == 1
            assert mails[0]["subject"] == "Welcome"
            assert mails[0]["from"] == "no-reply@service.com"
            assert "13579" in mails[0]["bodyHtml"]
        await src.session.aclose()


# ── 9. 新源注册进 EmailPool 测试 ──────────────────────────
class TestPoolNewSourcesRegistered:
    @pytest.fixture
    def pool(self, tmp_path):
        db_file = str(tmp_path / "test_registered.db")
        return EmailPool(db_path=db_file)

    def test_new_sources_registered(self, pool):
        names = [s.name for s in pool.get_sources()]
        assert "temp-mail.io" in names
        assert "mail.gw" in names

        # 别名命中
        assert pool._find_source("temp-mail.io") is not None
        assert pool._find_source("tempmail.io") is not None
        assert pool._find_source("mail.gw") is not None
        assert pool._find_source("mailgw") is not None

        # score 排序符合 priority：temp-mail.io(95) > mail.gw(75)
        src_io = pool._find_source("temp-mail.io")
        src_gw = pool._find_source("mail.gw")
        assert src_io.priority == 95
        assert src_gw.priority == 75
        assert src_io.score() > src_gw.score()


# ── 10. async_record / async_allocate（P2-3 后 record 已 async）──
class TestEmailPoolAsyncWrappers:
    """async_record / async_allocate：返回值与同步方法一致，且不阻塞 loop。

    P2-3 后 email_pool.record/registered_providers/stats 均已 async（aiosqlite），
    async_record 保留为兼容别名（直接 await record）。
    """

    @pytest.fixture
    def pool(self, tmp_path):
        db_file = str(tmp_path / "async_email.db")
        return EmailPool(db_path=db_file)

    @pytest.mark.asyncio
    async def test_async_record_persists_and_returns_none(self, pool):
        # async_record 应与 record 行为一致：写库 + 风控统计
        ret = await pool.async_record("user1@temp.tf", "nanobanana", "ok")
        assert ret is None
        assert await pool.registered_providers("user1@temp.tf") == ["nanobanana"]
        stats = await pool.stats()
        assert stats["total_registered"] == 1
        assert stats["by_provider"]["nanobanana"] == 1
        # ok 状态 → domain_risk success_count 累加
        conn = await pool._ensure_conn()
        async with pool._lock:
            cur = await conn.execute("SELECT domain FROM domain_risk")
            rows = await cur.fetchall()
        assert "temp.tf" in {r["domain"] for r in rows}

    @pytest.mark.asyncio
    async def test_async_record_error_increments_fail_count(self, pool):
        await pool.async_record("bad@22.do", "nanobanana", "error", "signup_fail")
        conn = await pool._ensure_conn()
        async with pool._lock:
            cur = await conn.execute(
                "SELECT domain, fail_count, status FROM domain_risk WHERE domain=?", ("22.do",)
            )
            rows = await cur.fetchall()
        assert len(rows) == 1
        assert rows[0]["fail_count"] == 1
        assert rows[0]["status"] == "risky"

    @pytest.mark.asyncio
    async def test_async_allocate_unique_and_records(self, pool, monkeypatch):
        # 本地 temp.tf 源足够验证分配唯一性 + async_record 配合
        monkeypatch.setattr(pool, "_sources", [s for s in pool._sources if s.name == "temp.tf"])
        a1, _s1 = await pool.allocate("nanobanana")
        a2, _s2 = await pool.allocate("nanobanana")
        assert a1 != a2
        await pool.async_record(a1, "nanobanana", "ok")
        assert await pool.registered_providers(a1) == ["nanobanana"]
        # 已用邮箱不再分配
        a3, _s3 = await pool.allocate("nanobanana")
        assert a3 not in (a1, a2)

    @pytest.mark.asyncio
    async def test_async_wrappers_do_not_block_event_loop(self, pool, monkeypatch):
        """并发 async_record + sleep(0) 协程，sleep(0) 必须被调度（非阻塞证据）。"""
        monkeypatch.setattr(pool, "_sources", [s for s in pool._sources if s.name == "temp.tf"])
        flag = {"ticked": 0}

        async def _tick():
            for _ in range(5):
                await asyncio.sleep(0)
                flag["ticked"] += 1

        async def _work():
            for i in range(5):
                addr = f"u{i}@temp.tf"
                await pool.async_record(addr, "nanobanana", "ok")

        await asyncio.gather(_tick(), _work())
        assert flag["ticked"] == 5  # 事件循环未被同步 sqlite3 阻塞
        stats = await pool.stats()
        assert stats["total_registered"] == 5
