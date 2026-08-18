"""测试内置告警引擎。"""
from api.alerting import AlertRule, AlertEngine


def test_alert_rule_condition():
    """验证告警规则条件判断。"""
    rule = AlertRule(
        name="test_rule",
        severity="warning",
        message="测试告警",
        cooldown=1.0,
        check=lambda ctx: ctx.get("value", 0) > 100,
    )
    assert rule.check({"value": 200}) is True
    assert rule.check({"value": 50}) is False


def test_alert_engine_cooldown():
    """验证告警冷却机制。"""
    engine = AlertEngine()
    engine.add_rule(AlertRule(
        name="cooldown_test",
        severity="warning",
        message="冷却测试",
        cooldown=5.0,
        check=lambda ctx: True,
    ))
    result = engine.evaluate({"value": 1})
    assert len(result) == 1
    result2 = engine.evaluate({"value": 1})
    assert len(result2) == 0  # 冷却中


def test_alert_engine_empty():
    """验证无规则时告警引擎正常。"""
    engine = AlertEngine()
    # 清除默认规则后测试
    engine._rules.clear()
    result = engine.evaluate({"value": 1})
    assert result == []