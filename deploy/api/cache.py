"""内存 LRU 缓存（asyncio 安全）。用于首页/画廊/统计等低频变更的读路径缓存，降低 DB 读压。"""
import asyncio
import logging
import time
from collections import OrderedDict
from typing import Any

log = logging.getLogger("cache")


class LRUCache:
    """线程安全（asyncio.Lock）的 LRU 缓存，支持 TTL 自动过期。

    内部用 OrderedDict 实现 LRU 淘汰：get 命中时 move_to_end 标记为最近使用；
    set 超出 maxsize 时淘汰最久未用的项（popitem(last=False)）。
    后台协程 _reaper 每秒扫描所有项，清理过期条目。
    """

    def __init__(self, maxsize: int = 128, ttl: float = 5.0) -> None:
        self._maxsize = maxsize
        self._ttl = ttl
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._reaper_task: asyncio.Task | None = None

    @property
    def maxsize(self) -> int:
        return self._maxsize

    @property
    def ttl(self) -> float:
        return self._ttl

    # ── 公开 API ─────────────────────────────────────

    async def get(self, key: str) -> Any | None:
        """获取缓存值。命中且未过期则返回，否则返回 None。"""
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            deadline, value = entry
            if time.monotonic() > deadline:
                del self._data[key]
                return None
            # LRU：标记为最近使用
            self._data.move_to_end(key)
            return value

    async def set(self, key: str, value: Any) -> None:
        """设置缓存条目。超出 maxsize 淘汰最久未用。"""
        async with self._lock:
            now = time.monotonic()
            if key in self._data:
                self._data.move_to_end(key)
            else:
                while len(self._data) >= self._maxsize:
                    self._data.popitem(last=False)
            self._data[key] = (now + self._ttl, value)

    async def invalidate(self, key: str) -> None:
        """删除指定 key（如新图入库后主动失效画廊缓存）。"""
        async with self._lock:
            self._data.pop(key, None)

    async def clear(self) -> None:
        """清空所有缓存条目。"""
        async with self._lock:
            self._data.clear()

    # ── 后台 reaper ─────────────────────────────────

    def start_reaper(self) -> None:
        """启动后台过期清理协程（lifespan 中调用）。"""
        if self._reaper_task is not None:
            return
        self._reaper_task = asyncio.create_task(self._reaper_loop())

    async def stop_reaper(self) -> None:
        """停止后台 reaper 并清空缓存。"""
        if self._reaper_task is None:
            return
        self._reaper_task.cancel()
        try:
            await self._reaper_task
        except asyncio.CancelledError:
            pass
        self._reaper_task = None
        await self.clear()

    async def _reaper_loop(self) -> None:
        """每秒扫描一次，清理过期条目。"""
        try:
            while True:
                await asyncio.sleep(1.0)
                await self._purge_expired()
        except asyncio.CancelledError:
            # 停止前最后清理一次
            await self._purge_expired()
            raise

    async def _purge_expired(self) -> None:
        """清理所有已过期的条目。"""
        async with self._lock:
            now = time.monotonic()
            expired = [k for k, (d, _) in self._data.items() if now > d]
            for k in expired:
                del self._data[k]
            if expired:
                log.debug("LRU 缓存清理 %d 个过期条目", len(expired))

    # ── 调试 / 指标 ──────────────────────────────────

    @property
    def size(self) -> int:
        """当前缓存条目数（不额外加锁，仅用于调试/日志）。"""
        return len(self._data)

    async def snapshot(self) -> dict:
        """快照：条目数 + maxsize + TTL，供 /v1/healthz 等端点观察缓存状态。"""
        async with self._lock:
            return {
                "size": len(self._data),
                "maxsize": self._maxsize,
                "ttl": self._ttl,
            }