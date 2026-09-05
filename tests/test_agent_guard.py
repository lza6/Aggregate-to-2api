"""tests/test_agent_guard.py — P1-A4 provider Tier + PreToolUse 硬门禁测试。

验收：
- provider risk_tier：free/metered/paid 三档
- guard_paid_call：free/metered 始终放行；paid 未在白名单→拦截；paid 在白名单→放行
- is_destructive_command：DROP TABLE/DELETE FROM accounts/rm -rf/ 拦截；SELECT 放行
- 开关关闭：guard_paid_call 始终放行（零回归）
- add/remove paid allowlist
"""

from __future__ import annotations

import os

os.environ.setdefault("IF_PROVIDER_RISK_TIER", "1")


class _FakeProvider:
    """假 provider：可设置 risk_tier。"""

    def __init__(self, prefix: str, tier: str) -> None:
        self.prefix = prefix
        self.risk_tier = tier


def test_provider_tier_free():
    """free Tier provider 始终放行。"""
    from api.agent.guard import guard_paid_call

    p = _FakeProvider("imagefree", "free")
    assert guard_paid_call(p, "generate") is True


def test_provider_tier_metered():
    """metered Tier provider 始终放行（tryingopen 免费但有限额）。"""
    from api.agent.guard import guard_paid_call

    p = _FakeProvider("tryingopen", "metered")
    assert guard_paid_call(p, "generate") is True


def test_provider_tier_paid_blocked_by_default():
    """paid Tier provider 未在白名单→拦截（付费 API 红线默认预算=0）。"""
    from api.agent.guard import guard_paid_call, remove_from_paid_allowlist

    p = _FakeProvider("falai", "paid")
    # 确保不在白名单
    remove_from_paid_allowlist("falai")
    assert guard_paid_call(p, "generate") is False


def test_provider_tier_paid_allowed_after_whitelist():
    """paid Tier provider 加白名单后→放行（用户明确批准真实付费）。"""
    from api.agent.guard import add_to_paid_allowlist, guard_paid_call, is_paid_allowed, remove_from_paid_allowlist

    p = _FakeProvider("falai", "paid")
    add_to_paid_allowlist("falai")
    try:
        assert is_paid_allowed("falai") is True
        assert guard_paid_call(p, "generate") is True
    finally:
        remove_from_paid_allowlist("falai")
    assert is_paid_allowed("falai") is False


def test_destructive_command_drop_table():
    """DROP TABLE 拦截。"""
    from api.agent.guard import is_destructive_command

    assert is_destructive_command("DROP TABLE imagefree.db") is True
    assert is_destructive_command("drop table accounts") is True


def test_destructive_command_delete_accounts():
    """DELETE FROM accounts 拦截。"""
    from api.agent.guard import is_destructive_command

    assert is_destructive_command("DELETE FROM accounts WHERE 1=1") is True
    assert is_destructive_command("DELETE FROM email_registry") is True


def test_destructive_command_rm_rf():
    """rm -rf / 和 git reset --hard 拦截。"""
    from api.agent.guard import is_destructive_command

    assert is_destructive_command("rm -rf /") is True
    assert is_destructive_command("git reset --hard HEAD~3") is True
    assert is_destructive_command("git push --force origin main") is True


def test_destructive_command_select_allowed():
    """SELECT 放行（非破坏性）。"""
    from api.agent.guard import is_destructive_command

    assert is_destructive_command("SELECT * FROM accounts") is False
    assert is_destructive_command("INSERT INTO accounts VALUES(...)") is False


def test_destructive_command_empty():
    """空命令不拦截。"""
    from api.agent.guard import is_destructive_command

    assert is_destructive_command("") is False
    assert is_destructive_command("   ") is False


def test_guard_disabled_returns_true(monkeypatch):
    """IF_PROVIDER_RISK_TIER=0 → guard_paid_call 始终放行（零回归）。"""
    import api.agent.guard as guard_mod

    monkeypatch.setattr(guard_mod, "PROVIDER_RISK_TIER_ENABLED", False)
    p = _FakeProvider("falai", "paid")
    assert guard_mod.guard_paid_call(p, "generate") is True


def test_get_provider_tier_none():
    """provider=None → free（默认）。"""
    from api.agent.guard import ProviderRiskTier, get_provider_tier

    assert get_provider_tier(None) == ProviderRiskTier.FREE


def test_get_provider_tier_from_provider():
    """从 provider 实例取 risk_tier。"""
    from api.agent.guard import ProviderRiskTier, get_provider_tier

    p = _FakeProvider("falai", "paid")
    assert get_provider_tier(p) == ProviderRiskTier.PAID


def test_allow_destructive_command_allowlist():
    """破坏性命令加 allowlist 后放行（运维明确授权）。"""
    from api.agent.guard import allow_destructive_command, is_destructive_command

    cmd = "DROP TABLE temp_debug"
    allow_destructive_command(cmd)
    assert is_destructive_command(cmd) is False
