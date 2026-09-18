"""电商技能合规护栏测试（指南 P1-5，commerce-agents 对标）。纯本地。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.skills.ecommerce.fence import (  # noqa: E402
    check_compliance,
    fence_ecommerce_payload,
)


def test_absolute_claim_flagged():
    issues = check_compliance("全网最低价，顶级品质")
    assert any(i.rule == "absolute_claim" for i in issues)
    assert any("全网最低" in i.match or "顶级" in i.match for i in issues)


def test_medical_claim_flagged():
    issues = check_compliance("本品可治愈失眠")
    assert any(i.rule == "medical_claim" and "治愈" in i.match for i in issues)


def test_data_claim_flagged_without_backing():
    issues = check_compliance("续航 36 小时")
    assert any(i.rule == "data_claim" for i in issues)


def test_clean_text_passes():
    assert check_compliance("深空黑配色，主动降噪功能，适合通勤") == []


def test_payload_rejected_on_absolute():
    res = fence_ecommerce_payload(
        driver="visual-driven",
        prompts=["全国第一的主图设计"],
    )
    assert res.rejected
    assert res.alternative != ""


def test_payload_ok_with_data_claim_only():
    res = fence_ecommerce_payload(
        driver="visual-driven",
        prompts=["续航 36 小时（附实验室报告背书）"],
    )
    assert res.ok
    assert any(i.rule == "data_claim" for i in res.issues)  # 提示性，不拦截


def test_payload_rejected_on_medical():
    res = fence_ecommerce_payload(storyboard=[{"copy": "祛除湿气，药到病除"}])
    assert res.rejected


def test_empty_payload_ok():
    res = fence_ecommerce_payload()
    assert res.ok and res.issues == []
