"""QueueSettings 子配置。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class QueueSettings(BaseModel):
    """队列 / Worker 配置组。"""

    max_queue: int = 2000
    admin_queue_max: int = 200
    high_queue_max: int = 500
    normal_queue_max: int = 1500
    workers: int = 10
    worker_auto: bool = False
    workers_min: int = 4
    workers_max: int = 16
    worker_scale_up_threshold: int = 200
    worker_scale_down_threshold: int = 20
    worker_idle_seconds: int = 90
    persistent_queue_enabled: bool = False
    persistent_queue_db: str = "data/queue.db"
    dlq_enabled: bool = True
    dlq_max_retries: int = 3
    dlq_retention_days: int = 7

    @classmethod
    def from_settings(cls, s: Any) -> QueueSettings:
        """从 Settings 实例提取字段构造 QueueSettings。"""
        return cls(
            max_queue=s.max_queue,
            admin_queue_max=s.admin_queue_max,
            high_queue_max=s.high_queue_max,
            normal_queue_max=s.normal_queue_max,
            workers=s.workers,
            worker_auto=s.if_worker_auto,
            workers_min=s.if_workers_min,
            workers_max=s.if_workers_max,
            worker_scale_up_threshold=s.if_worker_scale_up_threshold,
            worker_scale_down_threshold=s.if_worker_scale_down_threshold,
            worker_idle_seconds=s.if_worker_idle_seconds,
            persistent_queue_enabled=s.if_persistent_queue_enabled,
            persistent_queue_db=s.if_persistent_queue_db,
            dlq_enabled=s.if_dlq_enabled,
            dlq_max_retries=s.if_dlq_max_retries,
            dlq_retention_days=s.if_dlq_retention_days,
        )
