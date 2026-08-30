"""M5-E1 补测：alerting 冷却抑制与多规则并行触发。

覆盖 api/alerting.py 缺失分支（should_trigger 冷却内/外、evaluate 多规则并行、默认规则命中）。
"""
from __future__ import annotations

import time

from api.alerting import AlertEngine, AlertRule


def test_should_trigger_respects_cooldown():
    """冷却期内不重复触发；冷却结束可再次触发。"""
    rule = AlertRule(
        name="r",
        severity="warning",
        message="m",
        check=lambda ctx: True,
        cooldown=0.05,
    )
    assert rule.should_trigger({}) is True  # 首次触发
    assert rule.should_trigger({}) is False  # 冷却中
    time.sleep(0.06)
    assert rule.should_trigger({}) is True  # 冷却结束


def test_should_trigger_condition_false_never_triggers():
    """条件为 False 时永不触发，且不更新 _last_triggered。"""
    rule = AlertRule(
        name="r",
        severity="warning",
        message="m",
        check=lambda ctx: ctx.get("hit", False),
        cooldown=0.01,
    )
    assert rule.should_trigger({"hit": False}) is False
    assert rule.should_trigger({"hit": True}) is True
    # 条件不满足不影响冷却计数
    assert rule.should_trigger({"hit": False}) is False


def test_evaluate_multiple_rules_in_parallel():
    """多条规则同时命中 → 返回多条告警，各自独立冷却。"""
    engine = AlertEngine()
    engine._rules.clear()
    engine.add_rule(AlertRule(
        name="a", severity="warning", message="A",
        check=lambda ctx: True, cooldown=100.0,
    ))
    engine.add_rule(AlertRule(
        name="b", severity="critical", message="B",
        check=lambda ctx: ctx.get("hit_b", False), cooldown=100.0,
    ))
    result = engine.evaluate({"hit_b": True})
    names = {r["name"] for r in result}
    assert names == {"a", "b"}
    # 再评估：a 在冷却，b 在冷却 → 空
    assert engine.evaluate({"hit_b": True}) == []


def test_default_rule_queue_backlog_triggers():
    """内置默认规则 queued>1000 触发。"""
    engine = AlertEngine()
    result = engine.evaluate({"queued": 1001})
    assert any(r["name"] == "queue_backlog" for r in result)


def test_default_rule_high_error_rate_triggers():
    """内置默认规则错误率>20% 触发（需 window_requests>0）。"""
    engine = AlertEngine()
    result = engine.evaluate({"window_requests": 100, "window_errors": 30})
    assert any(r["name"] == "high_error_rate" for r in result)


def test_default_rule_high_error_rate_no_requests_no_trigger():
    """window_requests=0 时不触发（防除零）。"""
    engine = AlertEngine()
    result = engine.evaluate({"window_requests": 0, "window_errors": 999})
    assert not any(r["name"] == "high_error_rate" for r in result)


def test_default_rule_solver_circuit_open():
    """solver_circuit_open 命中。"""
    engine = AlertEngine()
    result = engine.evaluate({"solver_circuit_open": True})
    assert any(r["name"] == "solver_circuit_open" for r in result)


def test_default_rule_token_pool_empty():
    """token_pool_empty 命中。"""
    engine = AlertEngine()
    result = engine.evaluate({"token_pool_empty": True})
    assert any(r["name"] == "token_pool_empty" for r in result)


def test_default_rule_provider_down():
    """provider_down 命中。"""
    engine = AlertEngine()
    result = engine.evaluate({"provider_down": True})
    assert any(r["name"] == "provider_down" for r in result)


def test_default_rule_provider_consecutive_failures():
    """连续失败>=10 命中。"""
    engine = AlertEngine()
    result = engine.evaluate({"max_consecutive_failures": 10})
    assert any(r["name"] == "provider_consecutive_failures" for r in result)


def test_default_rule_ip_batch_block():
    """封禁 IP>=20 命中。"""
    engine = AlertEngine()
    result = engine.evaluate({"blocked_ip_count": 20})
    assert any(r["name"] == "ip_batch_block" for r in result)


def test_default_rule_auth_error_surge():
    """AUTH.001 错误>=30 命中。"""
    engine = AlertEngine()
    result = engine.evaluate({"auth_error_count": 30})
    assert any(r["name"] == "auth_error_surge" for r in result)


def test_evaluate_entry_has_required_fields():
    """触发的告警条目包含 name/severity/message/timestamp。"""
    engine = AlertEngine()
    engine._rules.clear()
    engine.add_rule(AlertRule(
        name="x", severity="critical", message="boom",
        check=lambda ctx: True, cooldown=100.0,
    ))
    result = engine.evaluate({})
    assert len(result) == 1
    entry = result[0]
    assert entry["name"] == "x"
    assert entry["severity"] == "critical"
    assert entry["message"] == "boom"
    assert "timestamp" in entry


def test_add_rule_appends():
    """add_rule 追加到规则列表。"""
    engine = AlertEngine()
    before = len(engine._rules)
    engine.add_rule(AlertRule(
        name="custom", severity="warning", message="m",
        check=lambda ctx: False, cooldown=1.0,
    ))
    assert len(engine._rules) == before + 1
    assert engine._rules[-1].name == "custom"
