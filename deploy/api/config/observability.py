"""ObservabilitySettings 子配置。"""
from __future__ import annotations

from pydantic import BaseModel


class ObservabilitySettings(BaseModel):
    """可观测性 / 治理配置组。"""

    health_check_interval: int = 60
    health_check_enabled: bool = True
    alert_check_interval: int = 60