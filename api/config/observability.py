"""ObservabilitySettings 子配置。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ObservabilitySettings(BaseModel):
    """可观测性 / 治理配置组。"""

    health_check_interval: int = 60
    health_check_enabled: bool = True
    alert_check_interval: int = 60

    @classmethod
    def from_settings(cls, s: Any) -> ObservabilitySettings:
        """从 Settings 实例提取字段构造 ObservabilitySettings。"""
        return cls(
            health_check_interval=s.if_health_check_interval,
            health_check_enabled=s.if_health_check_enabled,
            alert_check_interval=s.if_alert_check_interval,
        )
