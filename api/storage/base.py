"""分布式与单机存储适配层抽象接口（ISSUE-01）。

包含：
- DistributedLock: 分布式锁 / 互斥锁抽象
- RateLimiter: 滑动窗口与固定窗口限流抽象
- StorageAdapter: 综合存储适配后端基类
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DistributedLock(ABC):
    """分布式互斥锁契约。"""

    @abstractmethod
    async def acquire(self, key: str, holder: str, ttl: float = 60.0, timeout: float | None = None) -> str | None:
        """尝试获取锁。获取成功返回 token/锁标识，超时或失败返回 None。"""
        pass

    @abstractmethod
    async def release(self, key: str, token: str | None) -> bool:
        """释放锁。仅当 token 匹配时释放，防误释放他人锁。"""
        pass


class RateLimiter(ABC):
    """限流器契约。"""

    @abstractmethod
    async def is_allowed(self, key: str, limit: int, window: float = 60.0) -> bool:
        """检查 key 在 window 秒内是否未超 limit。如通过返回 True 并记录本次请求，超出返回 False。"""
        pass

    @abstractmethod
    async def get_count(self, key: str, window: float = 60.0) -> int:
        """获取当前窗口内的请求计数。"""
        pass

    @abstractmethod
    async def reset(self, key: str) -> None:
        """重置指定 key 的限流计数。"""
        pass


class StorageAdapter(ABC):
    """存储适配器基类，提供统一的分布式锁和限流服务。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """存储后端名称，如 'memory' / 'sqlite' / 'redis'。"""
        pass

    @property
    @abstractmethod
    def lock(self) -> DistributedLock:
        """获取锁管理器。"""
        pass

    @property
    @abstractmethod
    def rate_limiter(self) -> RateLimiter:
        """获取限流器。"""
        pass

    @abstractmethod
    async def startup(self) -> None:
        """初始化存储后端资源。"""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """释放存储后端资源。"""
        pass
