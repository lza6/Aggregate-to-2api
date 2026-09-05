"""tests/test_adaptive_router_cooldown.py — P1-A5（M10）CooldownCache + Retry-After 测试。

验收：
- record_cooldown 让 provider 进入冷却期
- is_in_cooldown 冷却期内 True，过期 False
- select_best 冷却期内跳过该 provider
- record_retry_after 解析 Retry-After 头触发冷却
- node_snapshot 暴露 cooldown_until / retry_after_seconds
"""

from __future__ import annotations

import time


def test_record_cooldown_sets_cooldown_until():
    """record_cooldown 设置 cooldown_until。"""
    from api.adaptive_router import AdaptiveRouter

    r = AdaptiveRouter()
    r.record_cooldown("test_provider", retry_after_seconds=60)
    snap = r.node_snapshot()
    assert "test_provider" in snap
    assert snap["test_provider"]["cooldown_until"] > time.time()
    assert snap["test_provider"]["retry_after_seconds"] == 60.0


def test_is_in_cooldown_during_period():
    """冷却期内 is_in_cooldown=True。"""
    from api.adaptive_router import AdaptiveRouter

    r = AdaptiveRouter()
    r.record_cooldown("p", retry_after_seconds=60)
    assert r.is_in_cooldown("p") is True


def test_is_in_cooldown_expired():
    """冷却过期 is_in_cooldown=False。"""
    from api.adaptive_router import AdaptiveRouter

    r = AdaptiveRouter()
    r.record_cooldown("p", retry_after_seconds=0.01)  # 极短冷却
    time.sleep(0.02)
    assert r.is_in_cooldown("p") is False


def test_select_best_skips_cooldown_provider():
    """select_best 跳过冷却中的 provider，选其余。"""
    from api.adaptive_router import AdaptiveRouter

    r = AdaptiveRouter()
    # 让 p1 冷却，p2 可用
    r.record_cooldown("p1", retry_after_seconds=60)
    # p2 健康可路由
    picked = r.select_best(["p1", "p2"], model="test")
    assert picked == "p2"


def test_record_retry_after_parses_header():
    """record_retry_after 解析 Retry-After 头触发冷却。"""
    from api.adaptive_router import AdaptiveRouter

    r = AdaptiveRouter()
    r.record_retry_after("p", "120")
    assert r.is_in_cooldown("p") is True
    snap = r.node_snapshot()
    assert snap["p"]["retry_after_seconds"] == 120.0


def test_record_retry_after_none_no_op():
    """Retry-After 头为 None/空 → 不触发冷却。"""
    from api.adaptive_router import AdaptiveRouter

    r = AdaptiveRouter()
    r.record_retry_after("p", None)
    r.record_retry_after("p", "")
    assert r.is_in_cooldown("p") is False


def test_cooldown_releases_after_expiry():
    """冷却到期后 provider 恢复可用（select_best 能选中）。"""
    from api.adaptive_router import AdaptiveRouter

    r = AdaptiveRouter()
    r.record_cooldown("p1", retry_after_seconds=0.01)
    time.sleep(0.02)
    # 冷却到期，p1 应可被选中
    picked = r.select_best(["p1"], model="test")
    assert picked == "p1"


def test_node_snapshot_exposes_cooldown_fields():
    """node_snapshot 暴露 cooldown_until / retry_after_seconds 字段。"""
    from api.adaptive_router import AdaptiveRouter

    r = AdaptiveRouter()
    r.record_cooldown("p", retry_after_seconds=30)
    snap = r.node_snapshot()["p"]
    assert "cooldown_until" in snap
    assert "retry_after_seconds" in snap
