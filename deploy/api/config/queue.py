"""QueueSettings 子配置。"""
from __future__ import annotations

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