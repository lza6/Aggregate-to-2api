"""存储驱动工厂与全局单例管理器。"""
from __future__ import annotations

import logging
from typing import Optional

from .. import config
from .base import StorageAdapter
from .local import LocalStorageAdapter

log = logging.getLogger("storage")

_STORAGE_ADAPTER: Optional[StorageAdapter] = None


def get_storage_adapter() -> StorageAdapter:
    """获取当前配置的存储驱动单例（默认单机 SQLite/Memory，配置 Redis 时启用 Redis 驱动）。"""
    global _STORAGE_ADAPTER
    if _STORAGE_ADAPTER is not None:
        return _STORAGE_ADAPTER

    backend = getattr(config, "IF_STORAGE_BACKEND", "sqlite").lower()
    redis_url = getattr(config, "IF_REDIS_URL", None)

    if backend == "redis" and redis_url:
        try:
            from .redis_adapter import RedisStorageAdapter
            adapter = RedisStorageAdapter(redis_url)
            _STORAGE_ADAPTER = adapter
            log.info("启用 Redis 存储适配器 (IF_STORAGE_BACKEND=redis)")
            return adapter
        except Exception as e:
            log.warning("无法加载 Redis 适配器，回退至 LocalStorageAdapter: %s", e)

    _STORAGE_ADAPTER = LocalStorageAdapter()
    return _STORAGE_ADAPTER


def set_storage_adapter(adapter: Optional[StorageAdapter]) -> None:
    """用于测试或运行时注入自定义存储驱动。"""
    global _STORAGE_ADAPTER
    _STORAGE_ADAPTER = adapter
