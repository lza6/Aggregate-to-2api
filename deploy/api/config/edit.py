"""EditSettings 子配置。"""
from __future__ import annotations

from pydantic import BaseModel


class EditSettings(BaseModel):
    """图生图编辑配置组。"""

    edit_timeout: int = 3600
    task_hard_timeout: int = 480
    edit_concurrency_wait: int = 60
    edit_mutex_enabled: bool = True
    edit_lock_max_age: int = 1500
    edit_retry_max: int = 30
    edit_retry_interval: int = 20
    edit_proxy_file: str = ""
    edit_proxy_parallel: int = 1
    edit_proxy_max_inflight: int = 2
    edit_proxy_pool_size: int = 1
    edit_proxy_pool_idle_ttl: int = 180
    generate_timeout: int = 300
    generate_poll_interval: float = 2.0
    generate_max_attempts: int = 2
    txt_retry_max: int = 3
    txt_retry_backoff_base: int = 5
    sync_timeout: int = 300
    max_image_bytes: int = 4 * 1024 * 1024