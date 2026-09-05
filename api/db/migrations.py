"""P0-3: DB schema 初始化 + 增量迁移（从 db/core.py 拆出）。

职责：所有 CREATE TABLE / CREATE INDEX / ALTER TABLE 兼容迁移 DDL 集中于此。
连接池/批量写/WAL checkpoint 仍归 db/core.py；本模块只管 schema 形状。

公共入口：
- ``init_schema(conn, lock)``：在给定连接 + 锁内跑全部建表 + 索引 + 兼容补列。
  DB._init_schema 调用它，旧调用方 ``from api.db.core import DB`` 零感知。
"""

from __future__ import annotations

import asyncio
import logging

import aiosqlite

log = logging.getLogger("db")


async def _create_requests_table(conn: aiosqlite.Connection) -> None:
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS requests (
            id          TEXT PRIMARY KEY,
            prompt      TEXT,
            aspect_ratio TEXT,
            download    INTEGER DEFAULT 0,
            status      TEXT,
            image_url   TEXT,
            image_base64 TEXT,
            image_mime  TEXT,
            error       TEXT,
            created_at  REAL,
            started_at  REAL,
            finished_at REAL,
            duration_sec REAL
        );
        CREATE INDEX IF NOT EXISTS idx_requests_created ON requests(created_at);
        CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
        CREATE INDEX IF NOT EXISTS idx_requests_finished ON requests(finished_at);
    """)


async def _create_idempotency_table(conn: aiosqlite.Connection) -> None:
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            idempotency_key TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            created_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_idempotency_created ON idempotency_keys(created_at);
    """)


async def _create_dlq_table(conn: aiosqlite.Connection) -> None:
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS dead_letter_queue (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            model TEXT,
            error TEXT,
            attempts INT,
            created_at REAL,
            last_attempt_at REAL,
            raw_log TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_dlq_created ON dead_letter_queue(created_at);
    """)


async def _create_cache_store_table(conn: aiosqlite.Connection) -> None:
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS cache_store (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL,
            ttl         REAL NOT NULL,
            cached_at   REAL NOT NULL
        );
    """)


async def _create_chat_usage_table(conn: aiosqlite.Connection) -> None:
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            reasoning_tokens INTEGER DEFAULT 0,
            tool_calls INTEGER DEFAULT 0,
            duration_ms REAL DEFAULT 0,
            success INTEGER DEFAULT 1,
            proxy_used TEXT,
            error TEXT,
            cost_usd REAL DEFAULT 0,
            day TEXT,
            month TEXT,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chat_usage_created ON chat_usage(created_at);
        CREATE INDEX IF NOT EXISTS idx_chat_usage_model ON chat_usage(model, created_at);
    """)


async def _apply_chat_usage_migrations(conn: aiosqlite.Connection) -> None:
    """兼容迁移：旧表缺列则补（避免 create table 不重建旧库）。"""
    try:
        _cu = await conn.execute("PRAGMA table_info(chat_usage)")
        _ccols = {r[1] for r in await _cu.fetchall()}
        for _cname, _cddl in (
            ("cost_usd", "REAL DEFAULT 0"),
            ("day", "TEXT"),
            ("month", "TEXT"),
        ):
            if _cname not in _ccols:
                await conn.execute(f"ALTER TABLE chat_usage ADD COLUMN {_cname} {_cddl}")
        # 索引必须在 ALTER 补列后建，否则旧库（无 month 列）报 no such column。
        _ccols = {r[1] for r in await (await conn.execute("PRAGMA table_info(chat_usage)")).fetchall()}
        if "month" in _ccols:
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_usage_month ON chat_usage(month)")
        if "provider" in _ccols:
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_usage_provider ON chat_usage(provider, created_at)")
    except Exception:
        pass


async def _apply_request_migrations(conn: aiosqlite.Connection) -> None:
    """requests 表增量补列 + 复合索引。"""
    await conn.commit()
    cursor = await conn.execute("PRAGMA table_info(requests)")
    rows = await cursor.fetchall()
    cols = {r[1] for r in rows}
    for col, ddl in (
        ("image_base64", "TEXT"),
        ("image_mime", "TEXT"),
        ("type", "TEXT DEFAULT 'txt'"),
        ("model", "TEXT DEFAULT 'default'"),
        ("upstream_task_id", "TEXT"),
        ("day", "TEXT"),
        ("month", "TEXT"),
        ("proxy_used", "TEXT"),
        ("client_ip", "TEXT"),
        ("user_agent", "TEXT"),
        ("trace_id", "TEXT DEFAULT ''"),
    ):
        if col not in cols:
            await conn.execute(f"ALTER TABLE requests ADD COLUMN {col} {ddl}")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_created_status ON requests(created_at, status)")
    await conn.commit()


async def init_schema(conn: aiosqlite.Connection, lock: asyncio.Lock | None = None) -> None:
    """跑全部建表 + 索引 + 兼容补列迁移。

    若传入 lock，则在锁内执行（与原 DB._init_schema 行为一致：写连接[0] 的锁内跑）。
    """
    async def _run() -> None:
        await _create_requests_table(conn)
        await _create_idempotency_table(conn)
        await _create_dlq_table(conn)
        await _create_cache_store_table(conn)
        await _create_chat_usage_table(conn)
        await _apply_chat_usage_migrations(conn)
        await _apply_request_migrations(conn)

    if lock is not None:
        async with lock:
            await _run()
    else:
        await _run()


__all__ = ["init_schema"]
