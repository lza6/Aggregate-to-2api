"""统一健康状态机（A-04）。

HealthRegistry 整合 solver_guard、provider_health、DB 连接等散落的健康状态，
提供统一视图供 /v1/healthz 消费。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

log = logging.getLogger("health")


@dataclass
class HealthStatus:
    """单个组件的健康状态。"""

    component: str
    status: Literal["healthy", "degraded", "down"]
    last_check: float
    consecutive_failures: int = 0
    message: str = ""


class HealthRegistry:
    """统一健康注册表：register → check_all → overall_status。

    支持的 check_fn 签名：
    - async def check() -> bool | str | HealthStatus
    - def check() -> bool | str | HealthStatus
    bool: True=healthy, False=down
    str: "healthy"|"degraded"|"down" 或状态名
    HealthStatus: 直接使用
    """

    def __init__(self) -> None:
        self._components: dict[str, HealthStatus] = {}
        self._check_fns: dict[str, Callable] = {}

    def register(self, component: str, check_fn: Callable) -> None:
        """注册一个健康检查组件。"""
        self._check_fns[component] = check_fn
        self._components[component] = HealthStatus(
            component=component,
            status="healthy",
            last_check=time.time(),
            consecutive_failures=0,
            message="",
        )

    async def check_all(self) -> dict[str, HealthStatus]:
        """遍历所有组件执行健康检查，返回状态字典。"""
        for name, fn in self._check_fns.items():
            try:
                result = fn()
                if isinstance(result, Awaitable):
                    result = await result
                status, message = self._parse_result(result)
            except Exception as e:
                status = "down"
                message = str(e)
            old = self._components.get(name)
            consecutive = (old.consecutive_failures + 1) if status == "down" else 0
            self._components[name] = HealthStatus(
                component=name,
                status=status,  # type: ignore[arg-type]
                last_check=time.time(),
                consecutive_failures=consecutive,
                message=message,
            )
        return dict(self._components)

    @staticmethod
    def _parse_result(result: object) -> tuple[str, str]:
        """解析 check_fn 返回值为 (status, message)。"""
        if isinstance(result, HealthStatus):
            return result.status, result.message
        if isinstance(result, bool):
            return ("healthy", "") if result else ("down", "check failed")
        if isinstance(result, str):
            if result in ("healthy", "degraded", "down"):
                return result, ""  # type: ignore[return-value]
            if result in ("ok", "up", "alive"):
                return "healthy", result
            return "down", result
        return "healthy", ""

    def degraded_components(self) -> list[str]:
        """返回降级或不可用的组件名列表（按严重程度排序：down > degraded）。"""
        down = [n for n, s in self._components.items() if s.status == "down"]
        degraded = [n for n, s in self._components.items() if s.status == "degraded"]
        return down + degraded

    def overall_status(self) -> Literal["ok", "degraded", "down"]:
        """聚合所有组件：全部 healthy → ok, 有 degraded → degraded, 有 down → down。"""
        has_degraded = False
        for s in self._components.values():
            if s.status == "down":
                return "down"
            if s.status == "degraded":
                has_degraded = True
        return "degraded" if has_degraded else "ok"

    def snapshot(self) -> dict:
        """快照：整体状态 + 各组件详情。"""
        return {
            "status": self.overall_status(),
            "components": {
                n: {
                    "status": s.status,
                    "last_check": s.last_check,
                    "consecutive_failures": s.consecutive_failures,
                    "message": s.message,
                }
                for n, s in self._components.items()
            },
            "degraded": self.degraded_components(),
        }


# 模块级单例
health_registry = HealthRegistry()
