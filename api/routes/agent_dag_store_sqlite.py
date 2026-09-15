"""api/routes/agent_dag_store_sqlite.py — v10.0.0 DAG run SQLite 持久化 store。

与内存 _DagRunStore 同接口（upsert/get/list/cleanup），供路由层 _STORE 双实现切换：
- 缺省仍走内存（agent_dag_store.py），IF_DAG_STORE_BACKEND=sqlite 时切换到此实现
- 数据落独立 DB 文件（默认 data/dag_runs.db，避免与主任务库争锁，见 Red Team R-C）
- DB 异常一律降级内存（log.warning 不崩 worker，保活语义同 queue_store）
- v14 P2：restore_run 从 dict 快照反序列化 DagRun 对象（重启后续跑 /v1/agent/dag/{id}/resume）

表结构：
  dag_runs(run_id TEXT PK, name TEXT, status TEXT, nodes_json TEXT,
           error_summary TEXT, created_at REAL, finished_at REAL)
  node_traces(id INTEGER PK AUTOINCREMENT, run_id TEXT, node_id TEXT,
              status TEXT, result TEXT, error TEXT, attempt INTEGER,
              duration_ms REAL, condition TEXT, finished_at REAL)
    - v13 P0-7 节点级执行轨迹：每节点终态一条快照，GET run 时回填 nodes 轨迹
      （重启后重建完整轨迹；保留 run_id+node_id 索引供按 run 查询）
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any

import aiosqlite

if TYPE_CHECKING:
    from ..agent.dag import DagRun

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
        # v13 P0-7 节点轨迹表（每节点终态一条快照；append-only，按 run 查询重建轨迹）
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS node_traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                status TEXT NOT NULL,
                result TEXT,
                error TEXT,
                attempt INTEGER NOT NULL,
                duration_ms REAL NOT NULL,
                condition TEXT,
                finished_at REAL
            )
            """
        )
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_node_traces_run ON node_traces(run_id)")
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
            rows = await self._query("SELECT * FROM dag_runs WHERE run_id = ?", (run_id,))
            if rows:
                return await self._decorate_with_traces(self._deserialize(rows[0]))
        except Exception as exc:
            log.warning("dag_runs 查询降级内存: %s", exc)
        return self._memory.get(run_id)

    async def restore_run(self, run_id: str) -> DagRun | None:
        """v14 P2：把持久化 dict 快照反序列化为 DagRun 对象（重启后续跑入口）。

        nodes 由 public_state 快照重建 DagNode（配置+执行状态全量还原：status/result/
        error/attempt/started_at/finished_at/duration_ms/condition/depends_on），
        依赖索引（dependencies/upstreams）与 run 级状态（fail_fast/max_parallel/
        status/error_summary/created_at/finished_at）一并还原。缺失快照 → None。
        DB 异常降级内存快照读取（保活语义同 get）。
        """
        snapshot = await self.get(run_id)
        if snapshot is None:
            return None
        return self._snapshot_to_run(snapshot)

    async def _traces_for(self, run_id: str) -> list[dict[str, Any]]:
        """读取 run 的节点轨迹（按节点/时间序；v13 P0-7）。"""
        try:
            rows = await self._query(
                "SELECT node_id, status, result, error, attempt, duration_ms, condition, finished_at "
                "FROM node_traces WHERE run_id = ? ORDER BY id",
                (run_id,),
            )
            return rows
        except Exception as exc:
            log.warning("node_traces 查询降级: %s", exc)
            return []

    async def _decorate_with_traces(self, run: dict[str, Any]) -> dict[str, Any]:
        """把 node_traces 快照回填到 run.nodes 的 trace 字段（重启后重建完整轨迹）。"""
        traces = await self._traces_for(run["run_id"])
        if not traces:
            return run
        by_node: dict[str, list[dict[str, Any]]] = {}
        for t in traces:
            by_node.setdefault(t["node_id"], []).append(t)
        nodes = []
        for n in run.get("nodes", []):
            n = dict(n)
            n["traces"] = by_node.get(n.get("id"), [])
            nodes.append(n)
        run = dict(run)
        run["nodes"] = nodes
        return run

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
            runs = [
                self._memory[k] for k in sorted(self._memory, key=lambda k: self._memory[k]["created_at"], reverse=True)
            ]
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
                # v13 P0-7：级联清理节点轨迹（避免孤儿轨迹长期累积）
                for run_id in ids:
                    await self._execute("DELETE FROM node_traces WHERE run_id = ?", (run_id,))
            return len(ids)
        except Exception as exc:
            log.warning("dag_runs 清理降级: %s", exc)
            expired = [k for k, v in self._memory.items() if v["created_at"] < cutoff]
            for k in expired:
                self._memory.pop(k, None)
            return len(expired)

    async def append_trace(self, trace: dict[str, Any]) -> None:
        """追加一条节点轨迹快照（v13 P0-7；DB 异常降级静默，不破坏执行）。"""
        try:
            await self._execute(
                """
                INSERT INTO node_traces
                    (run_id, node_id, status, result, error, attempt, duration_ms, condition, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.get("run_id"),
                    trace.get("node_id"),
                    trace.get("status"),
                    trace.get("result"),
                    trace.get("error"),
                    trace.get("attempt", 0),
                    trace.get("duration_ms", 0.0),
                    trace.get("condition"),
                    trace.get("finished_at"),
                ),
            )
        except Exception as exc:
            log.warning("node_traces 写入降级: %s", exc)

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

    @staticmethod
    def _snapshot_to_run(snapshot: dict[str, Any]) -> DagRun:
        """把 get() 的 dict 快照重建为 DagRun 对象（v14 P2；幂等不可变还原）。

        快照缺 fail_fast/max_parallel（v10/v13 早期落库数据）时用引擎默认值兜底，
        不抛异常（历史数据兼容）；nodes 为空列表同样可还原为空 run。
        """
        from ..agent.dag import DagNode, DagRun

        nodes: dict[str, DagNode] = {}
        for item in snapshot.get("nodes") or []:
            node = DagNode(
                id=item["id"],
                kind=item.get("kind", "llm"),
                depends_on=list(item.get("depends_on") or []),
                prompt=item.get("prompt"),
                model=item.get("model"),
                retry=int(item.get("retry") or 0),
                condition=item.get("condition"),
            )
            node.status = item.get("status", "pending")
            node.result = item.get("result")
            node.error = item.get("error")
            node.attempt = int(item.get("attempt") or 0)
            node.started_at = item.get("started_at")
            node.finished_at = item.get("finished_at")
            node.duration_ms = float(item.get("duration_ms") or 0.0)
            nodes[node.id] = node

        run = DagRun(
            run_id=snapshot.get("run_id", ""),
            name=snapshot.get("name", ""),
            nodes=nodes,
            status=snapshot.get("status", "pending"),
            created_at=float(snapshot.get("created_at") or time.time()),
            finished_at=snapshot.get("finished_at"),
            fail_fast=bool(snapshot.get("fail_fast", True)),
            max_parallel=int(snapshot.get("max_parallel") or 4),
        )
        run.error_summary = snapshot.get("error_summary")
        for node_id, node in nodes.items():
            run.dependencies[node_id] = list(node.depends_on)
            for dep in node.depends_on:
                run.upstreams.setdefault(dep, []).append(node_id)
        return run


__all__ = ["DagRunSqliteStore"]
