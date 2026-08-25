"""持久化任务队列存储（WAL 模式，task_queue 表）。

设计在 api/db/__init__.py 的 QueueDB 之上或替代之，独立于 imagefree.db。
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

import aiosqlite

log = logging.getLogger("db.queue_store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_queue (
    task_id TEXT PRIMARY KEY,
    priority INTEGER NOT NULL DEFAULT 2,
    seq INTEGER NOT NULL,
    created_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS idx_task_queue_status ON task_queue(status);
CREATE INDEX IF NOT EXISTS idx_task_queue_order ON task_queue(priority, seq);
"""


class QueueStore:
    """基于 SQLite WAL 的持久化任务队列。"""

    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        self._open_lock = asyncio.Lock()

    async def open(self) -> None:
        async with self._open_lock:
            if self._conn is not None:
                return
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            self._conn = await aiosqlite.connect(self.path)
            self._conn.row_factory = aiosqlite.Row
            # 极限性能调优参数（v5.2）：与主库一致的写读无锁并发 + 内存缓存
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA synchronous=NORMAL")
            await self._conn.execute("PRAGMA busy_timeout=10000")
            await self._conn.execute("PRAGMA cache_size=-64000")      # 64MB
            await self._conn.execute("PRAGMA mmap_size=268435456")    # 256MB
            await self._conn.execute("PRAGMA temp_store=MEMORY")
            await self._conn.executescript(_SCHEMA)
            await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def enqueue(self, task_id: str, priority: int, seq: int) -> None:
        await self.open()
        await self._conn.execute(
            "INSERT OR REPLACE INTO task_queue(task_id, priority, seq, created_at, status)"
            " VALUES(?, ?, ?, ?, 'pending')",
            (task_id, priority, seq, time.time()),
        )
        await self._conn.commit()

    async def mark_processing(self, task_id: str) -> None:
        await self.open()
        await self._conn.execute(
            "UPDATE task_queue SET status='processing' WHERE task_id=?", (task_id,))
        await self._conn.commit()

    async def mark_completed(self, task_id: str) -> None:
        await self.open()
        await self._conn.execute("DELETE FROM task_queue WHERE task_id=?", (task_id,))
        await self._conn.commit()

    async def list_pending(self) -> list[tuple[int, int, str]]:
        """返回按 priority/seq 排序的 pending 任务 [(priority, seq, task_id)]。"""
        await self.open()
        cur = await self._conn.execute(
            "SELECT priority, seq, task_id FROM task_queue WHERE status = 'pending'"
            " ORDER BY priority ASC, seq ASC")
        rows = await cur.fetchall()
        return [(r["priority"], r["seq"], r["task_id"]) for r in rows]

    async def cleanup(self, retention_days: int = 7) -> dict:
        """清理超期 pending 记录，返回删除数。"""
        await self.open()
        cutoff = time.time() - retention_days * 86400
        cur = await self._conn.execute(
            "DELETE FROM task_queue WHERE status='pending' AND created_at < ?", (cutoff,))
        await self._conn.commit()
        return {"deleted": cur.rowcount}