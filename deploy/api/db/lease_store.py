"""SQLite 行级原子租约锁存储（替代文件系统 PID 锁）。

设计：edit_leases 表，key 为 PRIMARY KEY。
- acquire：单条 SQL 内原子完成「检查过期 + 覆盖写入」，SQLite 写事务串行保证排他。
- renew：持锁者按 token 续租（延长 expires_at）。
- release：持锁者按 token 释放（DELETE WHERE key=? AND token=?）。
- 异常宕机：无续租 → expires_at 过期 → 新 acquire 自动覆盖，杜绝僵尸死锁。
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

import aiosqlite

log = logging.getLogger("db.lease_store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS edit_leases (
    key TEXT PRIMARY KEY,
    holder TEXT NOT NULL,
    token TEXT NOT NULL,
    expires_at REAL NOT NULL,
    created_at REAL NOT NULL
);
"""


class LeaseStore:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        self._open_lock = asyncio.Lock()
        # 串行化本连接上的写事务。单连接并发执行 BEGIN IMMEDIATE 会互相冲突
        # （"cannot start a transaction within a transaction"），必须应用层互斥。
        self._tx_lock = asyncio.Lock()

    async def open(self) -> None:
        async with self._open_lock:
            if self._conn is not None:
                return
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            self._conn = await aiosqlite.connect(self.path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA synchronous=NORMAL")
            await self._conn.execute("PRAGMA busy_timeout=5000")
            await self._conn.executescript(_SCHEMA)
            await self._conn.commit()

    async def close(self) -> None:
        async with self._open_lock:
            async with self._tx_lock:
                if self._conn:
                    await self._conn.close()
                    self._conn = None

    async def acquire(self, key: str, holder: str, token: str, ttl: float) -> bool:
        """原子获取锁。当前无有效锁（expires_at 已过期或不存在）才成功。"""
        await self.open()
        now = time.time()
        async with self._tx_lock:
            async with self._conn.execute("BEGIN IMMEDIATE"):
                cur = await self._conn.execute(
                    "SELECT expires_at FROM edit_leases WHERE key=?", (key,))
                row = await cur.fetchone()
                if row and row["expires_at"] > now:
                    await self._conn.rollback()
                    return False
                await self._conn.execute(
                    "INSERT OR REPLACE INTO edit_leases(key, holder, token, expires_at, created_at)"
                    " VALUES(?, ?, ?, ?, ?)",
                    (key, holder, token, now + ttl, now),
                )
                await self._conn.commit()
                return True

    async def renew(self, key: str, token: str, new_ttl: float) -> bool:
        """持锁者续租。仅当 token 匹配且锁未过期时延长 expires_at。"""
        await self.open()
        now = time.time()
        async with self._tx_lock:
            async with self._conn.execute("BEGIN IMMEDIATE"):
                cur = await self._conn.execute(
                    "UPDATE edit_leases SET expires_at=? WHERE key=? AND token=? AND expires_at>?",
                    (now + new_ttl, key, token, now),
                )
                await self._conn.commit()
                return cur.rowcount > 0

    async def release(self, key: str, token: str) -> bool:
        """按 token 释放。防止误删他人新锁。"""
        await self.open()
        async with self._tx_lock:
            async with self._conn.execute("BEGIN IMMEDIATE"):
                cur = await self._conn.execute(
                    "DELETE FROM edit_leases WHERE key=? AND token=?", (key, token))
                await self._conn.commit()
                return cur.rowcount > 0

    async def get(self, key: str) -> dict | None:
        await self.open()
        cur = await self._conn.execute(
            "SELECT key, holder, token, expires_at, created_at FROM edit_leases WHERE key=?",
            (key,))
        row = await cur.fetchone()
        return dict(row) if row else None