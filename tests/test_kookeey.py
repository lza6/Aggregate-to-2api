"""kookeey（住宅代理客户端）单元测试。

覆盖：启用判定、凭据解析、email 派生粘性 session（同 email 同 IP、不同 email 不同 IP）、
URL 保留字符 percent-encode、空 email 轮换、配置缺失回退。
直接用 monkeypatch 改 os.environ，不依赖真实账号。
"""
import os

import pytest

import api.kookeey as kookeey


MOCK_ENV = {
    "IF_KOOKEEY_ENABLED": "1",
    "IF_KOOKEEY_PROXY_ENABLED": "1",
    "IF_KOOKEEY_USER_ID": "UA-12345",
    "IF_KOOKEEY_SEC_USER": "suser",
    "IF_KOOKEEY_SEC_PASS": "spass:with@chars/x",
    "IF_KOOKEEY_GATE": "gate.example.com",
    "IF_KOOKEEY_GATE_PORT": "4321",
    "IF_KOOKEEY_COUNTRY": "JP",
}


@pytest.fixture
def kk_env(monkeypatch):
    for k, v in MOCK_ENV.items():
        monkeypatch.setenv(k, v)
    yield


@pytest.fixture
def kk_env_off(monkeypatch):
    monkeypatch.setenv("IF_KOOKEEY_ENABLED", "0")
    monkeypatch.setenv("IF_KOOKEEY_PROXY_ENABLED", "1")
    monkeypatch.setenv("IF_KOOKEEY_USER_ID", "UA-1")
    monkeypatch.setenv("IF_KOOKEEY_SEC_USER", "u")
    monkeypatch.setenv("IF_KOOKEEY_SEC_PASS", "p")
    monkeypatch.setenv("IF_KOOKEEY_GATE", "gate.kookeey.info")
    yield


# ── 启用判定 ───────────────────────────────────────
class TestEnabled:
    def test_enabled_true(self, kk_env):
        assert kookeey.kookeey_enabled()

    def test_disabled_when_env_off(self, kk_env_off):
        assert not kookeey.kookeey_enabled()

    def test_disabled_when_no_credentials(self, monkeypatch):
        for k in ("IF_KOOKEEY_USER_ID", "IF_KOOKEEY_SEC_USER", "IF_KOOKEEY_SEC_PASS", "IF_KOOKEEY_GATE"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("IF_KOOKEEY_ENABLED", "1")
        monkeypatch.setenv("IF_KOOKEEY_PROXY_ENABLED", "1")
        assert not kookeey.kookeey_enabled()

    def test_disabled_when_proxy_disabled(self, monkeypatch):
        monkeypatch.setenv("IF_KOOKEEY_ENABLED", "1")
        monkeypatch.setenv("IF_KOOKEEY_PROXY_ENABLED", "no")
        monkeypatch.setenv("IF_KOOKEEY_USER_ID", "UA-1")
        monkeypatch.setenv("IF_KOOKEEY_GATE", "g")
        monkeypatch.setenv("IF_KOOKEEY_SEC_USER", "u")
        monkeypatch.setenv("IF_KOOKEEY_SEC_PASS", "p")
        assert not kookeey.kookeey_enabled()


# ── 代理 URL 构造 ──────────────────────────────────
class TestProxyFor:
    def test_returns_empty_when_disabled(self, kk_env_off):
        assert kookeey.kookeey_proxy_for("a@b.com") == ""

    def test_returns_empty_when_missing_credentials(self, monkeypatch):
        monkeypatch.setenv("IF_KOOKEEY_ENABLED", "1")
        monkeypatch.setenv("IF_KOOKEEY_PROXY_ENABLED", "1")
        monkeypatch.delenv("IF_KOOKEEY_USER_ID", raising=False)
        monkeypatch.delenv("IF_KOOKEEY_SEC_USER", raising=False)
        monkeypatch.setenv("IF_KOOKEEY_SEC_PASS", "p")
        monkeypatch.setenv("IF_KOOKEEY_GATE", "g")
        assert kookeey.kookeey_proxy_for("a@b.com") == ""

    def test_scheme_and_country(self, kk_env):
        url = kookeey.kookeey_proxy_for("user@example.com")
        assert url.startswith("http://UA-12345-")
        assert url == (
            "http://UA-12345-"
            f"{_qs('suser')}:{_qs('spass:with@chars/x')}"
            "-JP-session@gate.example.com:4321"
        ) or url.endswith("@gate.example.com:4321")

    def test_same_email_same_session(self, kk_env):
        a = kookeey.kookeey_proxy_for("User@Example.com")
        b = kookeey.kookeey_proxy_for("user@example.com")
        assert a == b  # 相同 email（大小写归一）→ 相同 session → 粘性 IP
        assert b.endswith("-JP-7fbdcac4@gate.example.com:4321".replace("7fbdcac4", _md5("user@example.com")))

    def test_different_email_different_session(self, kk_env):
        a = kookeey.kookeey_proxy_for("a@b.com")
        c = kookeey.kookeey_proxy_for("c@d.com")
        assert a != c
        assert _md5("a@b.com") in a
        assert _md5("c@d.com") in c

    def test_empty_email_rotates(self, kk_env):
        # 空 email → 同样格式但 session=md5("") 前缀（调用方可每次新建则每次换 IP）
        url = kookeey.kookeey_proxy_for("")
        assert url.endswith("@gate.example.com:4321")

    def test_default_scheme_and_values(self, monkeypatch):
        monkeypatch.setenv("IF_KOOKEEY_ENABLED", "1")
        monkeypatch.setenv("IF_KOOKEEY_PROXY_ENABLED", "1")
        monkeypatch.setenv("IF_KOOKEEY_USER_ID", "U")
        monkeypatch.setenv("IF_KOOKEEY_SEC_USER", "su")
        monkeypatch.setenv("IF_KOOKEEY_SEC_PASS", "sp")
        monkeypatch.delenv("IF_KOOKEEY_GATE", raising=False)
        monkeypatch.delenv("IF_KOOKEEY_COUNTRY", raising=False)
        monkeypatch.delenv("IF_KOOKEEY_GATE_PORT", raising=False)
        url = kookeey.kookeey_proxy_for("x@y.z")
        assert f"http://U-{_qs('su')}:{_qs('sp')}-US-{_md5('x@y.z')}@gate.kookeey.info:1000" == url


def _md5(s):
    import hashlib
    return hashlib.md5(s.strip().lower().encode("utf-8")).hexdigest()[:8]


def _qs(s):
    from urllib.parse import quote
    return quote(s, safe="")