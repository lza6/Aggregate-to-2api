"""SQLite 动态 IP 封禁与风控规则存储（ISSUE-02）。

字段契约：
- ip: 主键 IP 地址
- block_type: 'block' (全量 403 拦截) | 'daily_limit' (每日调用上限拦截)
- daily_limit: 每日最大允许调用次数（当 block_type='daily_limit' 时生效，默认 1）
- reason: 封禁或限流原因
- expire_at: 过期时间戳（0 或 NULL 表示永久有效）
- created_at: 创建时间戳
- updated_at: 更新时间戳
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import aiosqlite

from .. import config

log = logging.getLogger("db.ip_blocklist")


class IPBlocklistStore:
    """异步 SQLite IP 封禁与风控存储。"""

    def __init__(self, db_path: Optional[str] = None):
        self._path = db_path or config.DB_FILE
        self._lock = asyncio.Lock()
        self._initialized = False

    async def _get_conn(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._path, timeout=10, isolation_level=None)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA busy_timeout=10000")
        return conn

    async def init_schema(self) -> None:
        """初始化表结构与索引。"""
        if self._initialized:
            return
        async with self._lock:
            conn = await self._get_conn()
            try:
                await conn.executescript("""
                    CREATE TABLE IF NOT EXISTS ip_blocklist (
                        ip          TEXT PRIMARY KEY,
                        block_type  TEXT NOT NULL DEFAULT 'block',
                        daily_limit INTEGER NOT NULL DEFAULT 1,
                        reason      TEXT DEFAULT '',
                        expire_at   REAL DEFAULT 0,
                        created_at  REAL NOT NULL,
                        updated_at  REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_ip_blocklist_expire ON ip_blocklist(expire_at);
                    CREATE INDEX IF NOT EXISTS idx_ip_blocklist_type ON ip_blocklist(block_type);
                """)
                await conn.commit()
                self._initialized = True
            finally:
                await conn.close()

    async def add_or_update(
        self,
        ip: str,
        block_type: str = "block",
        daily_limit: int = 1,
        reason: str = "",
        ttl_seconds: float = 0.0,
    ) -> dict:
        """添加或更新封禁记录。ttl_seconds <= 0 表示永久。"""
        await self.init_schema()
        now = time.time()
        expire_at = (now + ttl_seconds) if ttl_seconds > 0 else 0.0

        conn = await self._get_conn()
        try:
            await conn.execute(
                """
                INSERT INTO ip_blocklist (ip, block_type, daily_limit, reason, expire_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ip) DO UPDATE SET
                    block_type=excluded.block_type,
                    daily_limit=excluded.daily_limit,
                    reason=excluded.reason,
                    expire_at=excluded.expire_at,
                    updated_at=excluded.updated_at
                """,
                (ip, block_type, daily_limit, reason, expire_at, now, now),
            )
            await conn.commit()
            # 返回完整记录（含首次 created_at，更新时保持不变）
            cur = await conn.execute("SELECT * FROM ip_blocklist WHERE ip = ?", (ip,))
            row = await cur.fetchone()
            if row:
                return dict(row)
            return {
                "ip": ip,
                "block_type": block_type,
                "daily_limit": daily_limit,
                "reason": reason,
                "expire_at": expire_at,
                "created_at": now,
                "updated_at": now,
            }
        finally:
            await conn.close()

    async def remove(self, ip: str) -> bool:
        """移除指定 IP 封禁。"""
        await self.init_schema()
        conn = await self._get_conn()
        try:
            cur = await conn.execute("DELETE FROM ip_blocklist WHERE ip = ?", (ip,))
            await conn.commit()
            return cur.rowcount > 0
        finally:
            await conn.close()

    async def get(self, ip: str) -> Optional[dict]:
        """获取单个 IP 的生效规则（若已过期则返回 None 并异步触发清理）。"""
        await self.init_schema()
        now = time.time()
        conn = await self._get_conn()
        try:
            cur = await conn.execute("SELECT * FROM ip_blocklist WHERE ip = ?", (ip,))
            row = await cur.fetchone()
            if not row:
                return None
            data = dict(row)
            if data["expire_at"] and data["expire_at"] > 0 and data["expire_at"] < now:
                # 记录已过期，异步删除；无事件循环时静默跳过（由 cleanup 兜底）
                try:
                    asyncio.create_task(self.remove(ip))
                except RuntimeError:
                    pass
                return None
            return data
        finally:
            await conn.close()

    async def get_many(self, ips: list[str]) -> dict[str, dict]:
        """批量检查多个 IP 的生效规则。

        返回 {ip: rule}，仅包含未过期记录；已过期或不在表的 IP 不会出现在结果中。
        供多 IP 批量风控判定使用（单次 IN 查询，避免 N 次 SELECT）。
        """
        await self.init_schema()
        if not ips:
            return {}
        now = time.time()
        conn = await self._get_conn()
        try:
            placeholders = ",".join("?" * len(ips))
            cur = await conn.execute(f"SELECT * FROM ip_blocklist WHERE ip IN ({placeholders})", list(ips))
            rows = await cur.fetchall()
            out: dict[str, dict] = {}
            for r in rows:
                d = dict(r)
                if d["expire_at"] and d["expire_at"] > 0 and d["expire_at"] < now:
                    continue
                out[d["ip"]] = d
            return out
        finally:
            await conn.close()

    async def list_all(
        self,
        limit: int = 100,
        offset: int = 0,
        since_ts: float | None = None,
        updated_before: float | None = None,
    ) -> list[dict]:
        """列出有效封禁规则（P2-2 分页，防全量加载 OOM）。

        - limit：每页条数（钳到 [1, 10000]，默认 100）
        - offset：偏移量（游标分页，默认 0）
        - since_ts：仅返回 updated_at >= since_ts 的记录（可选时间游标）
        - updated_before：仅返回 updated_at < 该值的记录（keyset 游标，防并发写分页跳行）
        旧调用方传 limit=2000/10000 仍兼容（被钳到上限 10000）。
        """
        await self.init_schema()
        now = time.time()
        limit = max(1, min(limit, 10000))
        offset = max(0, offset)
        conn = await self._get_conn()
        try:
            if updated_before is not None:
                # keyset 游标：下一批取 updated_at < 上页最小 updated_at，严格递减防重复/漏
                cur = await conn.execute(
                    "SELECT * FROM ip_blocklist"
                    " WHERE (expire_at = 0 OR expire_at > ?) AND updated_at < ?"
                    " ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (now, float(updated_before), limit, offset),
                )
            elif since_ts is not None:
                cur = await conn.execute(
                    "SELECT * FROM ip_blocklist"
                    " WHERE (expire_at = 0 OR expire_at > ?) AND updated_at >= ?"
                    " ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (now, float(since_ts), limit, offset),
                )
            else:
                cur = await conn.execute(
                    "SELECT * FROM ip_blocklist"
                    " WHERE expire_at = 0 OR expire_at > ?"
                    " ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (now, limit, offset),
                )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def get_by_ip(self, ip: str) -> dict | None:
        """按 IP 精确查询单条封禁规则（P3 cache-miss 单行回源，避免 30s 全量同步窗口内漏放行）。"""
        await self.init_schema()
        now = time.time()
        conn = await self._get_conn()
        try:
            cur = await conn.execute(
                "SELECT * FROM ip_blocklist WHERE ip = ? AND (expire_at = 0 OR expire_at > ?)",
                (ip, now),
            )
            row = await cur.fetchone()
            return dict(row) if row else None
        finally:
            await conn.close()

    async def count(self, since_ts: float | None = None) -> int:
        """有效封禁规则总数（P2-2，不加载全部数据，单 SELECT COUNT）。

        供分页页码与 stats 端点使用，避免 list_all(limit=10000) 全量加载进内存。
        """
        await self.init_schema()
        now = time.time()
        conn = await self._get_conn()
        try:
            if since_ts is not None:
                cur = await conn.execute(
                    "SELECT COUNT(*) FROM ip_blocklist"
                    " WHERE (expire_at = 0 OR expire_at > ?) AND updated_at >= ?",
                    (now, float(since_ts)),
                )
            else:
                cur = await conn.execute(
                    "SELECT COUNT(*) FROM ip_blocklist WHERE expire_at = 0 OR expire_at > ?",
                    (now,),
                )
            row = await cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            await conn.close()

    async def count_by_type(self) -> dict[str, int]:
        """按 block_type 统计有效封禁的精确分布（P3 审查：替代 list_all 样本估算）。

        单 SELECT GROUP BY，不加载明细行；>1000 条时仍精确（样本估算会失真）。
        """
        await self.init_schema()
        now = time.time()
        conn = await self._get_conn()
        try:
            cur = await conn.execute(
                "SELECT block_type, COUNT(*) AS n FROM ip_blocklist"
                " WHERE expire_at = 0 OR expire_at > ? GROUP BY block_type",
                (now,),
            )
            rows = await cur.fetchall()
            return {r["block_type"]: int(r["n"]) for r in rows}
        finally:
            await conn.close()

    async def cleanup_expired(self) -> int:
        """清理已过期记录。"""
        await self.init_schema()
        now = time.time()
        conn = await self._get_conn()
        try:
            cur = await conn.execute("DELETE FROM ip_blocklist WHERE expire_at > 0 AND expire_at < ?", (now,))
            await conn.commit()
            return cur.rowcount
        finally:
            await conn.close()


# 单例
ip_blocklist_store = IPBlocklistStore()
