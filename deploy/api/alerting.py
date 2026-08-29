"""内置告警引擎 — 无需外部 Prometheus + AlertManager。

为独立部署提供轻量告警能力：规则评估 + 冷却抑制 + 日志触达。
"""
import logging
import time
from typing import Callable

log = logging.getLogger("imagefree_api.alerting")


class AlertRule:
    """一条告警规则。

    参数:
        name: 规则名（唯一标识）
        severity: 严重级别（warning / critical）
        message: 告警描述
        check: 条件函数，接收 ctx dict 返回 bool
        cooldown: 冷却时间（秒），冷却期间不重复触发
    """

    def __init__(
        self,
        name: str,
        severity: str,
        message: str,
        check: Callable[[dict], bool],
        cooldown: float = 300.0,
    ):
        self.name = name
        self.severity = severity
        self.message = message
        self.check = check
        self.cooldown = cooldown
        self._last_triggered: float = 0.0

    def should_trigger(self, ctx: dict) -> bool:
        """判断是否应触发告警（检查条件 + 冷却）。"""
        if not self.check(ctx):
            return False
        now = time.time()
        if now - self._last_triggered < self.cooldown:
            return False
        self._last_triggered = now
        return True


class AlertEngine:
    """告警引擎 — 管理规则集、评估上下文、触发告警。"""

    def __init__(self):
        self._rules: list[AlertRule] = []
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        """注册内置默认规则。"""
        self.add_rule(AlertRule(
            name="queue_backlog", severity="warning",
            message="排队任务数超过 1000",
            check=lambda ctx: ctx.get("queued", 0) > 1000, cooldown=300.0,
        ))
        self.add_rule(AlertRule(
            name="high_error_rate", severity="critical",
            message="错误率超过 20%（近 5 分钟窗口）",
            check=lambda ctx: (
                ctx.get("window_requests", 0) > 0 and
                ctx.get("window_errors", 0) / ctx.get("window_requests", 1) > 0.2
            ), cooldown=300.0,
        ))
        self.add_rule(AlertRule(
            name="solver_circuit_open", severity="critical",
            message="求解器熔断已开启 >=30s",
            check=lambda ctx: ctx.get("solver_circuit_open", False), cooldown=60.0,
        ))
        self.add_rule(AlertRule(
            name="token_pool_empty", severity="warning",
            message="token 池空超过 10s",
            check=lambda ctx: ctx.get("token_pool_empty", False), cooldown=120.0,
        ))
        self.add_rule(AlertRule(
            name="provider_down", severity="warning",
            message="提供商持续不可用 >5min",
            check=lambda ctx: ctx.get("provider_down", False), cooldown=300.0,
        ))
        self.add_rule(AlertRule(
            name="provider_consecutive_failures", severity="warning",
            message="单个提供商连续失败次数超阈值（≥10）",
            check=lambda ctx: ctx.get("max_consecutive_failures", 0) >= 10, cooldown=300.0,
        ))
        self.add_rule(AlertRule(
            name="ip_batch_block", severity="critical",
            message="IP 批量封禁/限流数量超阈值（≥20）",
            check=lambda ctx: ctx.get("blocked_ip_count", 0) >= 20, cooldown=300.0,
        ))
        self.add_rule(AlertRule(
            name="auth_error_surge", severity="warning",
            message="AUTH.001 错误在近窗口内超阈值（≥30）",
            # ctx['auth_error_count'] 为近窗口增量（breakdown 引擎在窗口期外重置，
            # 由 bg_tasks 用 count_of - 上轮快照计算），避免进程内累计值造成永久告警。
            check=lambda ctx: ctx.get("auth_error_count", 0) >= 30, cooldown=300.0,
        ))

    def add_rule(self, rule: AlertRule) -> None:
        """添加一条告警规则。"""
        self._rules.append(rule)

    def evaluate(self, ctx: dict) -> list[dict]:
        """评估所有规则，返回被触发的告警条目列表。"""
        triggered: list[dict] = []
        for rule in self._rules:
            if rule.should_trigger(ctx):
                entry = {
                    "name": rule.name,
                    "severity": rule.severity,
                    "message": rule.message,
                    "timestamp": time.time(),
                }
                log.warning("告警触发 [%s/%s]: %s", rule.severity, rule.name, rule.message)
                triggered.append(entry)
        return triggered


# 全局单例
alert_engine = AlertEngine()