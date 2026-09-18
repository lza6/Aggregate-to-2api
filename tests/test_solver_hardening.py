"""求解器加固测试（指南 P2-1，captcha-solver 对标）。

覆盖：SSRF 逐 IP 校验（validate_solver_url/_is_private_ip 既有实现锁定）、
cf_clearance 回放元数据（bound_domain/created_at 透传 + validate_replay 各场景）。
纯本地，无网络。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.captcha.protocol import (  # noqa: E402
    CF_CLEARANCE_SOLVER,
    TURNSTILE_SOLVER,
    CaptchaResult,
    from_cf_clearance,
    from_turnstile,
    validate_replay,
)
from api.solver_guard import _is_private_ip, validate_solver_url  # noqa: E402


# ── SSRF 守卫（既有实现锁定）────────────────────────────────
def test_validate_solver_url_accepts_local_and_https():
    assert validate_solver_url("http://127.0.0.1:8001") is True
    assert validate_solver_url("https://solver.example.com:8443") is True


def test_validate_solver_url_rejects_bad_scheme_and_link_local():
    assert validate_solver_url("file:///etc/passwd") is False
    assert validate_solver_url("169.254.169.254") is False  # 云元数据（无 scheme）


def test_private_ip_guard_rejects_link_local():
    assert _is_private_ip("169.254.169.254") is True  # 链路本地=禁止（云元数据防 SSRF）
    assert _is_private_ip("10.0.0.1") is False  # 内网允许
    assert _is_private_ip("127.0.0.1") is False  # 回环允许（本地 cf_solver）


# ── 回放元数据透传 ──────────────────────────────────────────
def test_from_cf_clearance_passthrough_metadata():
    d = {
        "cf_clearance": "ck123",
        "cookies": [{"name": "cf_clearance", "value": "ck123"}],
        "user_agent": "Mozilla/5.0",
        "elapsed_ms": 42.0,
        "bound_domain": "imagefree.net",
        "created_at": 1000.0,
    }
    r = from_cf_clearance(d)
    assert r.solver == CF_CLEARANCE_SOLVER
    assert r.bound_domain == "imagefree.net"
    assert r.created_at == 1000.0
    assert r.ok


def test_captcha_result_default_metadata():
    r = CaptchaResult()
    assert r.bound_domain == "" and r.created_at == 0.0
    assert r.ok is False


def test_from_turnstile_no_metadata():
    r = from_turnstile("tok", 1.0)
    assert r.solver == TURNSTILE_SOLVER
    assert r.bound_domain == ""


# ── validate_replay 各场景 ───────────────────────────────────
def _cf_result(**kw):
    base = dict(token="ck", solver=CF_CLEARANCE_SOLVER, bound_domain="imagefree.net",
                user_agent="UA-1", created_at=time.time())
    base.update(kw)
    return CaptchaResult(**base)


def test_replay_ok_when_matching():
    r = _cf_result()
    assert validate_replay(r, "imagefree.net", user_agent="UA-1") == []


def test_replay_domain_mismatch():
    r = _cf_result()
    reasons = validate_replay(r, "evil.example.com")
    assert any("domain 不匹配" in x for x in reasons)


def test_replay_ua_mismatch():
    r = _cf_result()
    reasons = validate_replay(r, "imagefree.net", user_agent="UA-2")
    assert any("user_agent 不匹配" in x for x in reasons)


def test_replay_expired():
    r = _cf_result(created_at=time.time() - 7200)
    reasons = validate_replay(r, "imagefree.net", max_age_seconds=1800)
    assert any("过期" in x for x in reasons)


def test_replay_turnstile_bypass():
    r = from_turnstile("tok", 1.0)
    assert validate_replay(r, "anything") == []


def test_replay_no_binding_bypass():
    r = CaptchaResult(token="ck", solver=CF_CLEARANCE_SOLVER)
    assert validate_replay(r, "anything") == []
