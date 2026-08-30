"""内存 LRU 缓存（asyncio 安全）。用于首页/画廊/统计等低频变更的读路径缓存，降低 DB 读压。

IMP-11: 支持持久化回写 DB。set 时同步写入 cache_store 表；后台 reaper 每轮清理后
flush 变更到 DB；stop 时全量刷新；start 时从 DB 恢复缓存，避免重启后空窗期。
"""

import asyncio
import json
import logging
import time
from collections import OrderedDict
from typing import Any

log = logging.getLogger("cache")


class _DbPending:
    """挂起变更缓冲区：批量写回 DB，减少单次写入频率。"""

    __slots__ = ("upserts", "deletes")

    def __init__(self) -> None:
        self.upserts: list[tuple[str, str, float]] = []
        self.deletes: list[str] = []


class LRUCache:
    """线程安全（asyncio.Lock）的 LRU 缓存，支持 TTL 自动过期 + IMP-11 持久化回写。

    内部用 OrderedDict 实现 LRU 淘汰：get 命中时 move_to_end 标记为最近使用；
    set 超出 maxsize 时淘汰最久未用的项（popitem(last=False)）。
    后台协程 _reaper 每秒扫描所有项，清理过期条目。

    若传入 persist_db（DB 实例），则：
    - set/invalidate 时同步写入 DB 变更缓冲区
    - 后台 reaper 每轮扫描后批量 flush 到 DB
    - shutdown 时 flush 全部条目到 DB
    - 启动时从 DB 加载恢复缓存，避免重启后空窗期
    """

    def __init__(self, maxsize: int = 128, ttl: float = 5.0, persist_db: object | None = None) -> None:
        self._maxsize = maxsize
        self._ttl = ttl
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._reaper_task: asyncio.Task | None = None
        # IMP-11: 持久化回写
        self._persist_db = persist_db
        self._pending = _DbPending()

    @property
    def maxsize(self) -> int:
        return self._maxsize

    @property
    def ttl(self) -> float:
        return self._ttl

    # ── 序列化 / 反序列化 ───────────────────────────

    @staticmethod
    def _serialize(value: Any) -> str | None:
        """将任意值序列化为 JSON 字符串。失败返回 None 跳过持久化。"""
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            log.warning("缓存值序列化失败，跳过持久化: %s", type(value).__name__)
            return None

    @staticmethod
    def _deserialize(raw: str) -> Any:
        """从 JSON 字符串反序列化缓存值。"""
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            log.warning("缓存值反序列化失败，丢弃: %.80s", raw)
            return None

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
                    evicted_key, evicted = self._data.popitem(last=False)
                    if self._persist_db:
                        j = self._serialize(evicted[1])
                        if j is not None:
                            self._pending.upserts.append((evicted_key, j, self._ttl))
            self._data[key] = (now + self._ttl, value)
        if self._persist_db:
            j = self._serialize(value)
            if j is not None:
                self._pending.upserts.append((key, j, self._ttl))

    async def invalidate(self, key: str) -> None:
        """删除指定 key（如新图入库后主动失效画廊缓存）。"""
        async with self._lock:
            self._data.pop(key, None)
        if self._persist_db:
            self._pending.deletes.append(key)

    async def invalidate_prefix(self, prefix: str) -> None:
        """按前缀批量失效（如画廊缓存 "gallery:" 前缀下所有 limit 变体）。"""
        async with self._lock:
            expired = [k for k in self._data if k.startswith(prefix)]
            for k in expired:
                del self._data[k]
        if self._persist_db:
            for k in expired:
                self._pending.deletes.append(k)

    async def clear(self) -> None:
        """清空所有缓存条目。"""
        async with self._lock:
            self._data.clear()

    # ── 持久化 API ───────────────────────────────────

    async def restore_from_db(self) -> int:
        """从 DB cache_store 表恢复缓存条目，返回恢复数。"""
        if not self._persist_db:
            return 0
        try:
            entries = await self._persist_db.load_cache_snapshot()
        except Exception as e:
            log.warning("缓存从 DB 恢复失败: %s", e)
            return 0
        if not entries:
            return 0
        async with self._lock:
            for key, value_json, remaining_ttl in entries:
                value = self._deserialize(value_json)
                if value is None:
                    continue
                if key in self._data:
                    continue
                self._data[key] = (time.monotonic() + remaining_ttl, value)
                while len(self._data) >= self._maxsize:
                    self._data.popitem(last=False)
        log.info("缓存从 DB 恢复 %d 个条目", len(entries))
        return len(entries)

    async def _flush_pending_to_db(self) -> None:
        """将挂起的变更 flush 到 DB（异步调用，在 _lock 外执行）。"""
        if not self._persist_db:
            return
        async with self._lock:
            upserts = list(self._pending.upserts)
            deletes = list(self._pending.deletes)
            self._pending.upserts.clear()
            self._pending.deletes.clear()
        try:
            if upserts:
                await self._persist_db.save_cache_batch(upserts)
            if deletes:
                await self._persist_db.delete_cache_batch(deletes)
        except Exception as e:
            log.warning("缓存持久化 flush 失败: %s", e)

    async def flush_to_db(self) -> None:
        """公开方法：强制 flush 所有挂起变更到 DB（stop 时调用）。"""
        await self._flush_pending_to_db()

    # ── 后台 reaper ─────────────────────────────────

    def start_reaper(self) -> None:
        """启动后台过期清理协程（lifespan 中调用）。"""
        if self._reaper_task is not None:
            return
        self._reaper_task = asyncio.create_task(self._reaper_loop())

    async def stop_reaper(self) -> None:
        """停止后台 reaper，flush 持久化后清空缓存。"""
        if self._reaper_task is None:
            return
        self._reaper_task.cancel()
        try:
            await self._reaper_task
        except asyncio.CancelledError:
            pass
        self._reaper_task = None
        await self._flush_all_to_db()
        await self.clear()

    async def _flush_all_to_db(self) -> None:
        """将内存中所有条目持久化到 DB（stop 时调用）。"""
        if not self._persist_db:
            return
        entries = []
        now = time.monotonic()
        for key, (deadline, value) in list(self._data.items()):
            remaining = deadline - now
            if remaining <= 0:
                continue
            j = self._serialize(value)
            if j is not None:
                entries.append((key, j, remaining))
        self._pending.upserts.clear()
        if entries:
            try:
                await self._persist_db.save_cache_batch(entries)
                log.info("缓存全量持久化: %d 个条目", len(entries))
            except Exception as e:
                log.warning("缓存全量持久化失败: %s", e)

    async def _reaper_loop(self) -> None:
        """每秒扫描一次，清理过期条目 + 每轮 flush 持久化。"""
        try:
            flush_counter = 0
            while True:
                await asyncio.sleep(1.0)
                await self._purge_expired()
                flush_counter += 1
                if flush_counter >= 5 and self._persist_db:
                    flush_counter = 0
                    await self._flush_pending_to_db()
        except asyncio.CancelledError:
            await self._purge_expired()
            await self._flush_pending_to_db()
            raise

    async def _purge_expired(self) -> None:
        """清理所有已过期的条目，过期前持久化到 DB。"""
        async with self._lock:
            now = time.monotonic()
            expired = [(k, v) for k, (d, v) in self._data.items() if now > d]
            for k, _ in expired:
                del self._data[k]
            if expired and self._persist_db:
                for key, _ in expired:
                    self._pending.deletes.append(key)
            if expired:
                log.debug("LRU 缓存清理 %d 个过期条目", len(expired))

    # ── 调试 / 指标 ──────────────────────────────────

    @property
    def size(self) -> int:
        return len(self._data)

    async def snapshot(self) -> dict:
        """快照：条目数 + maxsize + TTL + 持久化挂起变更数。"""
        async with self._lock:
            return {
                "size": len(self._data),
                "maxsize": self._maxsize,
                "ttl": self._ttl,
                "persist_pending_upserts": len(self._pending.upserts) if self._persist_db else 0,
            }
