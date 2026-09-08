"""api/routes/agent_dag_store_sqlite.py — v10.0.0 DAG run SQLite 持久化 store。

与内存 _DagRunStore 同接口（upsert/get/list/cleanup），供路由层 _STORE 双实现切换：
- 缺省仍走内存（agent_dag_store.py），IF_DAG_STORE_BACKEND=sqlite 时切换到此实现
- 数据落独立 DB 文件（默认 data/dag_runs.db，避免与主任务库争锁，见 Red Team R-C）
- DB 异常一律降级内存（log.warning 不崩 worker，保活语义同 queue_store）

表结构：
  dag_runs(run_id TEXT PK, name TEXT, status TEXT, nodes_json TEXT,
           error_summary TEXT, created_at REAL, finished_at REAL)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

import aiosqlite

log = logging.getLogger("routes.agent_dag_store_sqlite")

_DEFAULT_DB = os.getenv("IF_DAG_STORE_DB", "data/dag_runs.db")


class DagRunSqliteStore:
    """SQLite 持久化 run store（线程安全由 aiosqlite + 单 asyncio loop 保证）。"""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or _DEFAULT_DB
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        # 内存降级缓存：DB 不可用时保活（与 queue_store 降级语义一致）
        self._memory: dict[str, Any] = {}

    async def _ensure_open(self) -> aiosqlite.Connection:
        if self._db is not None:
            return self._db
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS dag_runs (
                run_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                nodes_json TEXT NOT NULL,
                error_summary TEXT,
                created_at REAL NOT NULL,
                finished_at REAL
            )
            """
        )
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_dag_runs_status ON dag_runs(status)")
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_dag_runs_created ON dag_runs(created_at)")
        await self._db.commit()
        return self._db

    async def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        """执行写语句；DB 异常抛给调用方（upsert 内降级）。"""
        db = await self._ensure_open()
        async with self._lock:
            await db.execute(sql, params)
            await db.commit()

    async def _query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        db = await self._ensure_open()
        async with self._lock, db.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def upsert(self, run: Any) -> None:
        """写入或更新一个 run（nodes 序列化为 nodes_json）。

        DB 异常降级内存：写入 self._memory，get 时优先 DB 后补内存。
        """
        try:
            await self._execute(
                """
                INSERT INTO dag_runs (run_id, name, status, nodes_json, error_summary, created_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    nodes_json=excluded.nodes_json,
                    error_summary=excluded.error_summary,
                    finished_at=excluded.finished_at
                """,
                (
                    run.run_id,
                    run.name,
                    run.status,
                    json.dumps([n.public_state() for n in run.nodes.values()], ensure_ascii=False),
                    run.error_summary,
                    run.created_at,
                    run.finished_at,
                ),
            )
        except Exception as exc:
            log.warning("dag_runs 写入降级内存: %s", exc)
            self._memory[run.run_id] = self._serialize(run)

    async def get(self, run_id: str) -> dict[str, Any] | None:
        try:
            rows = await self._query(
                "SELECT * FROM dag_runs WHERE run_id = ?", (run_id,)
            )
            if rows:
                return self._deserialize(rows[0])
        except Exception as exc:
            log.warning("dag_runs 查询降级内存: %s", exc)
        return self._memory.get(run_id)

    async def list(self, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
        """按创建时间倒序（最近在前）；可选 status 过滤。"""
        sql = "SELECT * FROM dag_runs"
        params: list[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        try:
            rows = await self._query(sql, tuple(params))
            return [self._deserialize(r) for r in rows]
        except Exception as exc:
            log.warning("dag_runs 列表降级内存: %s", exc)
            runs = [self._memory[k] for k in sorted(self._memory, key=lambda k: self._memory[k]["created_at"], reverse=True)]
            if status:
                runs = [r for r in runs if r.get("status") == status]
            return runs[:limit]

    async def cleanup(self, retention_days: float = 7, now: float | None = None) -> int:
        """删除早于 now-retention_days 的 run，返回删除数。"""
        now = now if now is not None else time.time()
        cutoff = now - retention_days * 86400
        try:
            rows = await self._query("SELECT run_id FROM dag_runs WHERE created_at < ?", (cutoff,))
            ids = [r["run_id"] for r in rows]
            if ids:
                await self._execute("DELETE FROM dag_runs WHERE created_at < ?", (cutoff,))
            return len(ids)
        except Exception as exc:
            log.warning("dag_runs 清理降级: %s", exc)
            expired = [k for k, v in self._memory.items() if v["created_at"] < cutoff]
            for k in expired:
                self._memory.pop(k, None)
            return len(expired)

    async def close(self) -> None:
        if self._db is not None:
            try:
                await self._db.close()
            except Exception:
                pass
            self._db = None

    @staticmethod
    def _serialize(run: Any) -> dict[str, Any]:
        return {
            "run_id": run.run_id,
            "name": run.name,
            "status": run.status,
            "nodes": [n.public_state() for n in run.nodes.values()],
            "error_summary": run.error_summary,
            "created_at": run.created_at,
            "finished_at": run.finished_at,
        }

    @staticmethod
    def _deserialize(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": row["run_id"],
            "name": row["name"],
            "status": row["status"],
            "nodes": json.loads(row["nodes_json"]),
            "error_summary": row["error_summary"],
            "created_at": row["created_at"],
            "finished_at": row["finished_at"],
        }


__all__ = ["DagRunSqliteStore"]
