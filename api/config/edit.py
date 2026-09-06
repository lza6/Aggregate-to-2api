"""EditSettings 子配置。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EditSettings(BaseModel):
    """图生图编辑配置组。"""

    edit_timeout: int = 3600
    task_hard_timeout: int = 480
    edit_concurrency_wait: int = 60
    edit_mutex_enabled: bool = True
    edit_lease_enabled: bool = Field(False, validation_alias="IF_EDIT_LEASE_ENABLED")
    edit_lease_ttl: int = Field(30, validation_alias="IF_EDIT_LEASE_TTL")
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

    @classmethod
    def from_settings(cls, s: Any) -> EditSettings:
        """从 Settings 实例提取字段构造 EditSettings。"""
        return cls(
            edit_timeout=s.edit_timeout,
            task_hard_timeout=s.task_hard_timeout,
            edit_concurrency_wait=s.edit_concurrency_wait,
            edit_mutex_enabled=s.edit_mutex_enabled,
            edit_lease_enabled=s.edit_lease_enabled,
            edit_lease_ttl=s.edit_lease_ttl,
            edit_lock_max_age=s.edit_lock_max_age,
            edit_retry_max=s.edit_retry_max,
            edit_retry_interval=s.edit_retry_interval,
            edit_proxy_file=s.edit_proxy_file,
            edit_proxy_parallel=s.edit_proxy_parallel,
            edit_proxy_max_inflight=s.if_edit_proxy_max_inflight,
            edit_proxy_pool_size=s.edit_proxy_pool_size,
            edit_proxy_pool_idle_ttl=s.edit_proxy_pool_idle_ttl,
            generate_timeout=s.generate_timeout,
            generate_poll_interval=s.generate_poll_interval,
            generate_max_attempts=s.generate_max_attempts,
            txt_retry_max=s.if_txt_retry_max,
            txt_retry_backoff_base=s.if_txt_retry_backoff_base,
            sync_timeout=s.sync_timeout,
            max_image_bytes=4 * 1024 * 1024,
        )
