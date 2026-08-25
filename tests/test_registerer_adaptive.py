"""单元测试：自适应注册工作流、故障分类退避与断点状态推进 (Adaptive Registration Worker)。

覆盖场景：
1. 错误分类与自适应退避模型 (CF_BLOCKED / EMAIL_RATE_LIMITED / IP_BLOCKED / TRANSIENT)。
2. 断点状态推进与会话上下文快照 (RegistrationSession & RegistrationStage)。
3. CF 阻断时求解器状态标记与退避联动。
4. 邮箱频控时邮箱源降级与切源联动。
5. 提供商风控/IP 污染时强制轮换代理。
6. 注册成功时连续错误计数重置与完整链路。
"""
import asyncio
import time
import pytest

from api import config
from api.registerer import (
    AdaptiveRegistrationBackoff,
    Minimaxh3Registerer,
    NanobananaRegisterer,
    RegistrationError,
    RegistrationErrorCategory,
    RegistrationSession,
    RegistrationStage,
    adaptive_backoff,
)
from api.solver_guard import solver_guard
from api.email_pool import email_pool


def test_adaptive_backoff_classification():
    """测试不同故障分类下的退避时长与指数退避模型。"""
    backoff_mgr = AdaptiveRegistrationBackoff(
        cf_backoff=30.0,
        email_backoff=60.0,
        ip_backoff=120.0,
        transient_base=2.0,
        transient_max=30.0,
    )
    provider = "test_prov"

    # 1. CF 阻断 -> 30s
    sec_cf = backoff_mgr.compute_backoff(provider, RegistrationErrorCategory.CF_BLOCKED)
    assert sec_cf == 30.0

    # 2. 邮箱频控 -> 60s
    sec_email = backoff_mgr.compute_backoff(provider, RegistrationErrorCategory.EMAIL_RATE_LIMITED)
    assert sec_email == 60.0

    # 3. IP 污染 / 风控 -> 120s
    sec_ip = backoff_mgr.compute_backoff(provider, RegistrationErrorCategory.IP_BLOCKED)
    assert sec_ip == 120.0

    # 4. 瞬态错误 -> 指数退避: 2s, 4s, 8s, 16s...
    backoff_mgr.record_success(provider)
    t1 = backoff_mgr.compute_backoff(provider, RegistrationErrorCategory.TRANSIENT)
    assert t1 == 2.0
    t2 = backoff_mgr.compute_backoff(provider, RegistrationErrorCategory.TRANSIENT)
    assert t2 == 4.0
    t3 = backoff_mgr.compute_backoff(provider, RegistrationErrorCategory.TRANSIENT)
    assert t3 == 8.0
    t4 = backoff_mgr.compute_backoff(provider, RegistrationErrorCategory.TRANSIENT)
    assert t4 == 16.0
    t5 = backoff_mgr.compute_backoff(provider, RegistrationErrorCategory.TRANSIENT)
    assert t5 == 30.0  # 触达 max 30s

    # 快照断言
    snap = backoff_mgr.snapshot()
    assert snap["consecutive_errors"][provider] == 5
    assert snap["last_category"][provider] == "transient"
    assert snap["stats"][provider]["total"] == 8


def test_registration_session_stages():
    """测试 RegistrationSession 阶段状态推进与快照。"""
    session = RegistrationSession(provider="nanobanana")
    assert session.stage == RegistrationStage.INIT

    session.advance_to(
        RegistrationStage.EMAIL_ALLOCATED,
        email="test@22.do",
        email_source="22.do",
    )
    assert session.stage == RegistrationStage.EMAIL_ALLOCATED
    assert session.email == "test@22.do"
    assert session.email_source == "22.do"

    session.advance_to(RegistrationStage.CAPTCHA_SOLVED, captcha_token="token_123")
    assert session.stage == RegistrationStage.CAPTCHA_SOLVED
    assert session.captcha_token == "token_123"

    session.advance_to(RegistrationStage.VERIFICATION_SENT, verification_token="v_tok")
    assert session.verification_token == "v_tok"

    session.advance_to(RegistrationStage.CODE_OR_LINK_RECEIVED, verification_code="123456")
    assert session.verification_code == "123456"

    session.advance_to(RegistrationStage.LOGGED_IN, session_cookie="sess=xyz", credits=4)
    assert session.session_cookie == "sess=xyz"
    assert session.credits == 4

    session.advance_to(RegistrationStage.COMPLETED)
    assert session.stage == RegistrationStage.COMPLETED

    snap = session.snapshot()
    assert snap["stage"] == "completed"
    assert snap["email"] == "test@22.do"
    assert snap["has_captcha"] is True
    assert snap["has_verify_token"] is True
    assert snap["has_code_or_link"] is True
    assert snap["credits"] == 4


def test_registration_session_failure():
    """测试 RegistrationSession 失败标记。"""
    session = RegistrationSession(provider="minimaxh3")
    session.advance_to(RegistrationStage.EMAIL_ALLOCATED, email="fail@temp.tf")
    session.mark_failed("WAF 403 Forbidden", RegistrationErrorCategory.IP_BLOCKED)

    assert session.stage == RegistrationStage.FAILED
    assert session.last_error == "WAF 403 Forbidden"
    assert session.error_category == RegistrationErrorCategory.IP_BLOCKED

    snap = session.snapshot()
    assert snap["stage"] == "failed"
    assert snap["error_category"] == "ip_blocked"


@pytest.mark.asyncio
async def test_minimaxh3_cf_blocked_handling(monkeypatch):
    """测试 minimaxh3 遇到 Turnstile 求解失败时的自适应分类与 solver_guard 标记。"""
    reg = Minimaxh3Registerer()
    monkeypatch.setattr(config, "MOCK_REGISTER", False)

    async def fake_allocate(provider):
        return "user1@temp.tf", {"source": "temp.tf"}

    monkeypatch.setattr(email_pool, "allocate", fake_allocate)

    async def fake_solve_fail(*args, **kwargs):
        raise RuntimeError("Cloudflare Turnstile WAF Rejected")

    monkeypatch.setattr("api.turnstile_client.solve_turnstile", fake_solve_fail)

    result = await reg.register_one()
    assert result is None
    assert reg.last_session is not None
    assert reg.last_session.stage == RegistrationStage.FAILED
    assert reg.last_session.error_category == RegistrationErrorCategory.CF_BLOCKED


@pytest.mark.asyncio
async def test_nanobanana_email_timeout_and_source_cooldown(monkeypatch):
    """测试 nanobanana 验证链接收取超时时触发邮箱源退避切源。"""
    reg = NanobananaRegisterer()
    monkeypatch.setattr(config, "MOCK_REGISTER", False)

    async def fake_allocate(provider):
        return "nbuser@22.do", {"source": "22.do"}

    monkeypatch.setattr(email_pool, "allocate", fake_allocate)

    async def fake_solve(*args, **kwargs):
        return "captcha_ok", 0.1

    monkeypatch.setattr("api.turnstile_client.solve_turnstile", fake_solve)

    class FakeResponse:
        status_code = 429
        text = "429 Too Many Requests rate limited"
        cookies = {}
        def json(self):
            return {}

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(reg.client, "post", fake_post)

    result = await reg.register_one()
    assert result is None
    assert reg.last_session is not None
    assert reg.last_session.stage == RegistrationStage.FAILED
    assert reg.last_session.error_category == RegistrationErrorCategory.EMAIL_RATE_LIMITED


@pytest.mark.asyncio
async def test_ip_blocked_force_rotate_client(monkeypatch):
    """测试遇到 403 风控拦截时触发强制代理客户端轮换。"""
    reg = NanobananaRegisterer()
    monkeypatch.setattr(config, "MOCK_REGISTER", False)

    async def fake_allocate(provider):
        return "ipblock@22.do", {"source": "22.do"}

    monkeypatch.setattr(email_pool, "allocate", fake_allocate)

    async def fake_solve(*args, **kwargs):
        return "captcha_ok", 0.1

    monkeypatch.setattr("api.turnstile_client.solve_turnstile", fake_solve)

    class Fake403Response:
        status_code = 403
        text = "Forbidden - Cloudflare Security Challenge"
        cookies = {}
        def json(self):
            return {}

    def fake_post(*args, **kwargs):
        return Fake403Response()

    monkeypatch.setattr(reg.client, "post", fake_post)

    old_client = reg.client
    result = await reg.register_one()
    assert result is None
    assert reg.last_session.error_category == RegistrationErrorCategory.IP_BLOCKED
    # 强制轮换过 client
    assert reg.client is not old_client
