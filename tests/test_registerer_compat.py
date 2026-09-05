"""P0-5: registerer.py 拆分为 registerer/ 包的兼容性契约测试。

验证拆分后所有旧 import 路径仍可用，公共符号签名不变。
"""

from __future__ import annotations

import httpx


def test_module_star_import():
    """`from api.registerer import *` 全部公共符号可见。"""
    from api import registerer as r

    # 公共类
    assert hasattr(r, "RegistrationStage")
    assert hasattr(r, "RegistrationErrorCategory")
    assert hasattr(r, "RegistrationError")
    assert hasattr(r, "RegistrationSession")
    assert hasattr(r, "AdaptiveRegistrationBackoff")
    assert hasattr(r, "NanobananaRegisterer")
    # 公共常量/单例
    assert hasattr(r, "MOCK_REGISTER")
    assert hasattr(r, "STAGE_LABELS")
    assert hasattr(r, "adaptive_backoff")
    assert hasattr(r, "build_registerers")
    # 公共工具函数
    for fn in (
        "_parse_iso_ts",
        "_browser_headers",
        "_th",
        "_extract_code",
        "_extract_verify_link",
        "_proxy_host",
        "_ip_to_proxy",
        "_mail_ai_extract_enabled",
        "_gen_password",
        "_session_data_from_cookies",
    ):
        assert hasattr(r, fn), f"missing public util: {fn}"


def test_explicit_import_paths():
    """各调用方实际使用的显式 import 路径全部可用。"""
    from api.registerer import (  # noqa: F401
        STAGE_LABELS,
        AdaptiveRegistrationBackoff,
        NanobananaRegisterer,
        RegistrationError,
        RegistrationErrorCategory,
        RegistrationSession,
        RegistrationStage,
        _browser_headers,
        _extract_code,
        _extract_verify_link,
        _gen_password,
        _ip_to_proxy,
        _mail_ai_extract_enabled,
        _parse_iso_ts,
        _proxy_host,
        _session_data_from_cookies,
        _th,
        adaptive_backoff,
        build_registerers,
    )


def test_legacy_attribute_access():
    """旧路径 `import api.registerer as r; r.X` 可用。"""
    import api.registerer as r

    assert r.RegistrationStage.INIT.value == "init"
    assert r.RegistrationStage.COMPLETED.value == "completed"
    assert r.RegistrationErrorCategory.CF_BLOCKED.value == "cf_blocked"
    assert callable(r.build_registerers)
    assert isinstance(r.adaptive_backoff, r.AdaptiveRegistrationBackoff)


def test_singleton_identity():
    """adaptive_backoff 单例一致（模块级唯一实例）。"""
    import api.registerer as r
    from api.registerer import adaptive_backoff

    assert adaptive_backoff is r.adaptive_backoff


def test_stage_labels_completeness():
    """STAGE_LABELS 覆盖全部阶段。"""
    from api.registerer import STAGE_LABELS, RegistrationStage

    for s in RegistrationStage:
        assert s.value in STAGE_LABELS, f"missing label: {s.value}"


def test_build_registerers_contract():
    """build_registerers() 返回 {nanobanana: NanobananaRegisterer}。"""
    from api.registerer import NanobananaRegisterer, build_registerers

    regs = build_registerers()
    assert set(regs) == {"nanobanana"}
    assert isinstance(regs["nanobanana"], NanobananaRegisterer)


def test_static_methods_callable():
    """NanobananaRegisterer 静态方法签名不变。"""
    from api.registerer import NanobananaRegisterer

    ok = httpx.Response(200, text='0:{"success":true,"data":{"rewardAmount":4}}')
    assert NanobananaRegisterer._claim_response_ok(ok) is True
    bad = httpx.Response(200, text='0:{"error":"failed"}')
    assert NanobananaRegisterer._claim_response_ok(bad) is False


def test_extract_code_link_contract():
    """_extract_code / _extract_verify_link 行为不变。"""
    from api.registerer import _extract_code, _extract_verify_link

    mail = {"subject": "Code", "bodyPreview": "Your code is 123456 valid", "bodyHtml": ""}
    assert _extract_code(mail) == "123456"
    assert _extract_code(None) is None

    link_mail = {"bodyHtml": '<a href="https://nanobanana-pro.com/api/auth/verify-email?token=abc123">verify</a>'}
    link = _extract_verify_link(link_mail)
    assert link is not None and "verify-email" in link


def test_browser_headers_contract():
    """_browser_headers 返回结构不变。"""
    from api.registerer import _browser_headers

    h = _browser_headers("https://example.com")
    assert h["Origin"] == "https://example.com"
    assert h["Referer"] == "https://example.com/"
    assert "User-Agent" in h
    h2 = _browser_headers("https://example.com", referer="https://example.com/x")
    assert h2["Referer"] == "https://example.com/x"


def test_proxy_host_contract():
    """_proxy_host 提取 host 不变。"""
    from api.registerer import _proxy_host

    assert _proxy_host(None) == ""
    assert _proxy_host("http://user:pass@1.2.3.4:8080") == "1.2.3.4"
    assert _proxy_host("socks5://5.6.7.8:1080") == "5.6.7.8"
