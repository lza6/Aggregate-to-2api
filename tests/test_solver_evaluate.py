"""solver evaluate 参数化测试（v18 P2-3，captcha-solver 对标）。纯本地。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.solver_guard import validate_solve_params  # noqa: E402


def test_valid_sitekey_hex_format():
    assert validate_solve_params("https://example.com", "0x" + "A" * 40) == []


def test_valid_sitekey_base64url():
    assert validate_solve_params("https://example.com", "a" * 40) == []


def test_short_sitekey_allowed_for_mock():
    # 参数化安全：短 sitekey（mock/测试）无注入字符即放行
    assert validate_solve_params("https://example.com", "sk") == []
    assert validate_solve_params("https://example.com", "short") == []


def test_injection_sitekey_rejected():
    reasons = validate_solve_params("https://example.com", "0x4AAAAAACE-XLGoQUckKKm_ anonymous; whitelist_admin")
    assert any("sitekey" in r for r in reasons)  # 空格/分号注入字符被拒绝
    reasons3 = validate_solve_params("https://example.com", 'sitekey" OR 1=1')
    assert any("sitekey" in r for r in reasons3)


def test_empty_sitekey_passes_format():
    # 空 sitekey（上游可能不带）不因格式拒绝（url 校验仍生效）
    assert validate_solve_params("https://example.com", "") == []


def test_invalid_url_scheme_rejected():
    reasons = validate_solve_params("file:///etc/passwd", "0x" + "A" * 40)
    assert any("url" in r for r in reasons)
    reasons2 = validate_solve_params("gopher://x", "0x" + "A" * 40)
    assert any("url" in r for r in reasons2)


def test_valid_url_passes():
    assert validate_solve_params("https://imagefree.net/page", "0x" + "B" * 40) == []
    assert validate_solve_params("http://127.0.0.1:8001", "0x" + "B" * 40) == []


def test_hook_rejects_invalid_params():
    import asyncio

    from api.turnstile_client import solve_turnstile

    with pytest.raises(Exception) as ei:
        asyncio.run(solve_turnstile(url="https://x", sitekey="bad!", timeout=5))
    assert "求解参数非法" in str(ei.value)
