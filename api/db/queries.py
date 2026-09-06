"""DB 业务查询/写入方法（Mixin）+ QueueDB（已废弃）+ task_to_public。

P0-F3 拆分：从 db/core.py 迁出 DB 类全部业务方法，组成 ``DBQueriesMixin``。
core.py 的 ``DB`` 继承本 mixin 获得这些方法，旧 ``from api.db.core import DB``
零感知。Mixin 依赖宿主类提供 ``_enqueue_write`` / ``_get_read_conn`` /
``_get_write_conn`` / ``_ensure_flushed`` / ``_connections`` / ``_conn_locks`` /
``_commit_count`` / ``_get_lock`` / ``_path``。连接池/批量写/WAL checkpoint 仍归
core.py。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any  # noqa: F401  (保留供后续 mypy strict 升级 dict→dict[str,Any] 使用)

import aiosqlite

from .. import base64_store, config
from ..telemetry import get_tracer

log = logging.getLogger("db")


class DBQueriesMixin:
    """DB 类的业务查询/写入方法 Mixin（P0-F3 从 core.py 拆出）。

    宿主类须提供连接池与批量写基础设施（见模块 docstring）。本 mixin 只含
    业务 SQL 拼装与结果塑形逻辑，不持有连接状态。
    """

    # ── 写 ────────────────────────────────────────
    async def create_request(
        self,
        task_id: str,
        prompt: str,
        aspect_ratio: str,
        download: bool,
        type_: str = "txt",
        model: str = "default",
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        tracer = get_tracer()
        with tracer.start_as_current_span(
            "db.create_request",
            attributes={"task.id": task_id, "task.type": type_, "task.model": model, "task.aspect_ratio": aspect_ratio},
        ):
            now = time.time()
            import datetime

            dt = datetime.datetime.fromtimestamp(now, tz=datetime.UTC)
            day = dt.strftime("%Y-%m-%d")
            month = dt.strftime("%Y-%m")
            trace_id = ""
            try:
                from ..context import get_current_trace_id

                trace_id = get_current_trace_id() or ""
            except Exception:
                pass
            await self._enqueue_write(
                "INSERT INTO requests (id, prompt, aspect_ratio, download, status, created_at,"
                " type, model, day, month, client_ip, user_agent, trace_id)"
                " VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task_id,
                    prompt,
                    aspect_ratio,
                    int(download),
                    now,
                    type_,
                    model,
                    day,
                    month,
                    client_ip,
                    user_agent,
                    trace_id,
                ),
            )

    async def mark_started(self, task_id: str) -> None:
        tracer = get_tracer()
        with tracer.start_as_current_span("db.mark_started", attributes={"task.id": task_id}):
            await self._enqueue_write(
                "UPDATE requests SET status='processing', started_at=? WHERE id=?",
                (time.time(), task_id),
            )

    async def mark_pending_again(self, task_id: str) -> None:
        """S-9: DLQ 重入队——重置为 pending 并清空错误信息。"""
        tracer = get_tracer()
        with tracer.start_as_current_span("db.mark_pending_again", attributes={"task.id": task_id}):
            await self._enqueue_write(
                "UPDATE requests SET status='pending', error=NULL, started_at=NULL,"
                " finished_at=NULL, duration_sec=NULL WHERE id=?",
                (task_id,),
            )

    async def mark_finished(
        self,
        task_id: str,
        status: str,
        image_url: str | None,
        error: str | None,
        duration_sec: float | None,
        image_base64: str | None = None,
        image_mime: str | None = None,
    ) -> None:
        tracer = get_tracer()
        with tracer.start_as_current_span(
            "db.mark_finished",
            attributes={"task.id": task_id, "task.status": status, "task.duration_sec": duration_sec or 0},
        ):
            if image_base64 and image_mime:
                image_base64 = base64_store.save_base64(task_id, image_base64, image_mime)
            await self._enqueue_write(
                "UPDATE requests SET status=?, image_url=?, image_base64=?, image_mime=?,"
                " error=?, finished_at=?, duration_sec=? WHERE id=?",
                (status, image_url, image_base64, image_mime, error, time.time(), duration_sec, task_id),
            )

    async def update_upstream_task(self, task_id: str, upstream_task_id: str) -> None:
        """记录上游生成任务 id，便于恢复孤儿槽位与排查。"""
        await self._enqueue_write(
            "UPDATE requests SET upstream_task_id=? WHERE id=?",
            (upstream_task_id, task_id),
        )

    async def update_proxy_used(self, task_id: str, proxy: str | None) -> None:
        """记录该任务使用的出口代理。"""
        if proxy is not None:
            await self._enqueue_write(
                "UPDATE requests SET proxy_used=? WHERE id=?",
                (proxy, task_id),
            )

    async def recover_stale_tasks(self, reason: str = "服务重启，任务中断", stale_after: float = 300.0) -> int:
        """启动时回收上次进程遗留的 pending/processing 孤儿任务。"""
        cutoff = time.time() - stale_after
        _, conn, conn_lock = await self._get_write_conn()
        async with conn_lock:
            cur = await conn.execute(
                "UPDATE requests SET status='error', error=?, finished_at=? "
                "WHERE status IN ('pending','processing') AND created_at < ?",
                (reason, time.time(), cutoff),
            )
            await conn.commit()
            return cur.rowcount

    # ── 读 ────────────────────────────────────────
    _PUBLIC_COLS = (
        "id",
        "status",
        "image_url",
        "image_base64",
        "image_mime",
        "error",
        "created_at",
        "duration_sec",
        "type",
        "model",
        "client_ip",
        "user_agent",
    )
    _TASK_LIST_COLS = (
        "id",
        "status",
        "image_url",
        "error",
        "created_at",
        "duration_sec",
        "type",
        "model",
        "aspect_ratio",
        "prompt",
        "client_ip",
        "user_agent",
    )
    _GALLERY_COLS = (
        "id",
        "status",
        "image_url",
        "image_mime",
        "error",
        "created_at",
        "finished_at",
        "duration_sec",
        "type",
        "model",
        "prompt",
        "aspect_ratio",
    )
    _ERROR_COLS = (
        "id",
        "status",
        "error",
        "created_at",
        "duration_sec",
        "type",
        "model",
        "prompt",
        "aspect_ratio",
    )

    async def get(self, task_id: str) -> dict | None:
        await self._ensure_flushed()
        conn = await self._get_read_conn()
        cursor = await conn.execute("SELECT * FROM requests WHERE id=?", (task_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    async def get_public(self, task_id: str) -> dict | None:
        """轻量查询：只取公共 API 响应字段（不含 prompt）。"""
        await self._ensure_flushed()
        cols = ", ".join(self._PUBLIC_COLS)
        conn = await self._get_read_conn()
        cursor = await conn.execute(f"SELECT {cols} FROM requests WHERE id=?", (task_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_dict(row, default=False)

    async def list_tasks(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        model: str | None = None,
        sort: str = "created_at",
    ) -> tuple[list[dict], int]:
        """任务列表查询（IMP-41）。"""
        await self._ensure_flushed()
        where = []
        params: list = []
        if status:
            where.append("status=?")
            params.append(status)
        if model:
            where.append("model=?")
            params.append(model)
        where_clause = (" WHERE " + " AND ".join(where)) if where else ""
        conn = await self._get_read_conn()
        total_cursor = await conn.execute(f"SELECT COUNT(*) FROM requests{where_clause}", params)
        total_row = await total_cursor.fetchone()
        total = int(total_row[0])
        allowed_sort = {"created_at", "duration_sec", "finished_at", "status", "model"}
        if sort not in allowed_sort:
            sort = "created_at"
        direction = "DESC" if sort in ("created_at", "finished_at") else "ASC"
        cols = ", ".join(self._TASK_LIST_COLS)
        data_cursor = await conn.execute(
            f"SELECT {cols} FROM requests{where_clause} ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        rows = await data_cursor.fetchall()
        items = [self._row_to_dict(r) for r in rows]
        return items, total

    async def recent_images(self, limit: int = 50) -> list[dict]:
        """画廊：最近完成的、有图的请求。"""
        await self._ensure_flushed()
        cols = ", ".join(self._GALLERY_COLS)
        conn = await self._get_read_conn()
        cursor = await conn.execute(
            f"SELECT {cols} FROM requests WHERE status='completed' AND image_url IS NOT NULL"
            " ORDER BY finished_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def recent_errors(self, limit: int = 20) -> list[dict]:
        """最近失败的请求（含错误原因/prompt），供在线排查。"""
        await self._ensure_flushed()
        cols = ", ".join(self._ERROR_COLS)
        conn = await self._get_read_conn()
        cursor = await conn.execute(
            f"SELECT {cols} FROM requests WHERE status='error'" " ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ── 统计 ──────────────────────────────────────
    async def stats_overview(self) -> dict:
        """总量 + 平均出图耗时。"""
        await self._ensure_flushed()
        conn = await self._get_read_conn()
        cursor = await conn.execute(
            "SELECT COUNT(*) AS total, "
            " SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS images, "
            " SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors, "
            " AVG(CASE WHEN status='completed' AND duration_sec IS NOT NULL"
            "         THEN duration_sec END) AS avg_duration"
            " FROM requests"
        )
        row = await cursor.fetchone()
        total, images, errors, avg_duration = row
        return {
            "total_requests": int(total or 0),
            "total_images": int(images or 0),
            "total_errors": int(errors or 0),
            "avg_duration_sec": round(float(avg_duration), 1) if avg_duration else None,
        }

    async def stats_daily(self, days: int = 14) -> list[dict]:
        """近 N 天：每天请求/出图/失败（IMP-07: 直接用 day 列）。"""
        await self._ensure_flushed()
        import datetime

        cutoff_dt = datetime.date.today() - datetime.timedelta(days=days)
        cutoff = cutoff_dt.strftime("%Y-%m-%d")
        conn = await self._get_read_conn()
        cursor = await conn.execute(
            "SELECT day, COUNT(*) AS total, "
            " SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS images, "
            " SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors"
            " FROM requests WHERE day >= ?"
            " GROUP BY day ORDER BY day",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        return [{"day": r[0], "total": r[1], "images": r[2], "errors": r[3]} for r in rows]

    async def stats_monthly(self, months: int = 12) -> list[dict]:
        """近 N 月：每月请求/出图/失败。"""
        await self._ensure_flushed()
        import datetime

        now = datetime.date.today()
        y, m = now.year, now.month
        for _ in range(months):
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        cutoff = f"{y:04d}-{m:02d}"
        conn = await self._get_read_conn()
        cursor = await conn.execute(
            "SELECT month, COUNT(*) AS total, "
            " SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS images, "
            " SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors"
            " FROM requests WHERE month >= ?"
            " GROUP BY month ORDER BY month",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        return [{"month": r[0], "total": r[1], "images": r[2], "errors": r[3]} for r in rows]

    # ── 增长治理（M7）──────────────────────────────
    async def cleanup(self, retention_days: int) -> dict:
        """TTL 清理：删除超期请求记录，回收 WAL 并 VACUUM 压缩文件。"""
        await self._ensure_flushed()
        cutoff = time.time() - retention_days * 86400
        conn0 = self._connections[0]
        db_cursor = await conn0.execute("PRAGMA database_list")
        db_row = await db_cursor.fetchone()
        path = db_row[2]
        size_before = os.path.getsize(path) if os.path.exists(path) else 0
        _, conn, conn_lock = await self._get_write_conn()
        async with conn_lock:
            cur = await conn.execute("DELETE FROM requests WHERE created_at < ?", (cutoff,))
            await conn.commit()
            deleted = cur.rowcount
            try:
                await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            try:
                await conn.execute("VACUUM")
            except Exception as e:
                log.warning("VACUUM 失败（可忽略，稍后自动重试）: %s", e)
            await conn.commit()
            try:
                await conn.execute("ANALYZE")
            except Exception:
                pass
        size_after = os.path.getsize(path) if os.path.exists(path) else 0
        return {"deleted": deleted, "size_before": size_before, "size_after": size_after}

    async def cleanup_batched(self, retention_days: int, batch_size: int = 5000) -> dict:
        """TTL 回收（分批，避免单条长 DELETE 锁表/占用内存）：删除超期请求记录。

        每批先 `SELECT id ... WHERE created_at < ? LIMIT ?` 选出超期 id（SQLite 默认构建
        不支持 `DELETE ... LIMIT`，故用 id 定位），再按 id 集合删除并提交一次；循环直到无
        超期行。最后统一做 WAL checkpoint + VACUUM + ANALYZE。供夜间 04:00 分批巡检使用。
        与 `cleanup()` 行为正交（cleanup 签名/行为保持不变），返回额外 `batches` 计数。
        """
        await self._ensure_flushed()
        cutoff = time.time() - retention_days * 86400
        conn0 = self._connections[0]
        db_cursor = await conn0.execute("PRAGMA database_list")
        db_row = await db_cursor.fetchone()
        path = db_row[2]
        size_before = os.path.getsize(path) if os.path.exists(path) else 0
        _, conn, conn_lock = await self._get_write_conn()
        deleted = 0
        batches = 0
        async with conn_lock:
            while True:
                sel = await conn.execute(
                    "SELECT id FROM requests WHERE created_at < ? LIMIT ?", (cutoff, batch_size)
                )
                rows = await sel.fetchall()
                if not rows:
                    break
                ids = [r[0] for r in rows]
                placeholders = ",".join("?" * len(ids))
                cur = await conn.execute(
                    f"DELETE FROM requests WHERE id IN ({placeholders})", ids
                )
                await conn.commit()
                deleted += cur.rowcount
                batches += 1
            try:
                await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            try:
                await conn.execute("VACUUM")
            except Exception as e:
                log.warning("VACUUM 失败（可忽略，稍后自动重试）: %s", e)
            await conn.commit()
            try:
                await conn.execute("ANALYZE")
            except Exception:
                pass
        size_after = os.path.getsize(path) if os.path.exists(path) else 0
        return {"deleted": deleted, "batches": batches, "size_before": size_before, "size_after": size_after}

    async def count(self) -> int:
        """总记录数（指标用）。"""
        await self._ensure_flushed()
        conn = await self._get_read_conn()
        cursor = await conn.execute("SELECT COUNT(*) FROM requests")
        row = await cursor.fetchone()
        return int(row[0])

    async def count_recent_requests(self, window_seconds: float = 60.0) -> int:
        """P-04: 统计过去 window_seconds 秒内创建的请求数。"""
        cutoff = time.time() - window_seconds
        await self._ensure_flushed()
        conn = await self._get_read_conn()
        cursor = await conn.execute("SELECT COUNT(*) FROM requests WHERE created_at >= ?", (cutoff,))
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _row_to_dict(row: aiosqlite.Row, default: bool = True) -> dict:
        keys = row.keys()
        d = dict(zip(keys, row))
        if "download" in d:
            d["download"] = bool(d["download"])
        d["duration_sec"] = round(d["duration_sec"], 1) if d.get("duration_sec") is not None else None
        d.setdefault("type", "txt")
        d.setdefault("model", "default")
        d.setdefault("upstream_task_id", None)
        d.setdefault("trace_id", "")
        # IMP-26: file:// 路径 → 读取文件内容还原 base64
        if "image_base64" in d and d.get("image_base64") is not None:
            val = d["image_base64"]
            if isinstance(val, str) and val.startswith("file://"):
                path = val[7:]
                try:
                    with open(path, encoding="utf-8") as f:
                        data = f.read()
                    if len(data) > 10 * 1024 * 1024:
                        log.warning("base64 文件超过 10MB 限制，跳过: %s", path)
                        d["image_base64"] = None
                    else:
                        d["image_base64"] = data
                except OSError:
                    d["image_base64"] = None
        return d

    # ── IMP-26: base64 文件治理 ─────────────────────
    async def get_base64_path(self, task_id: str) -> str | None:
        """返回 task_id 对应的 base64 文件路径，无文件时返回 None。"""
        await self._ensure_flushed()
        conn = await self._get_read_conn()
        cursor = await conn.execute("SELECT image_base64 FROM requests WHERE id=?", (task_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            return None
        val = str(row[0])
        if val.startswith("file://"):
            return val[7:]
        return None

    async def read_base64(self, task_id: str) -> str | None:
        """从文件读取 task_id 的 base64 字符串。"""
        path = await self.get_base64_path(task_id)
        if path is None:
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = f.read()
            if len(data) > 10 * 1024 * 1024:
                log.warning("base64 文件超过 10MB 限制，跳过 read_base64: %s", path)
                return None
            return data
        except OSError:
            return None

    def clean_base64_files(self, ttl: float) -> int:
        """清理过期 base64 缓存文件，返回删除数。"""
        return base64_store.clean_expired(ttl)

    # ── IMP-06: 幂等提交 ─────────────────────────────
    async def save_idempotency(self, key: str, task_id: str) -> None:
        """保存幂等 key → task_id 映射。"""
        await self._enqueue_write(
            "INSERT OR REPLACE INTO idempotency_keys (idempotency_key, task_id, created_at)" " VALUES (?, ?, ?)",
            (key, task_id, time.time()),
        )

    async def claim_idempotency(self, key: str, task_id: str) -> str:
        """原子抢占幂等 key：成功（首次）返回本 task_id；已存在返回先前 task_id。

        v7.6 P0 修复：save_idempotency 的 INSERT OR REPLACE + get/save 两步在并发下
        存在 TOCTOU——两个请求都通过 get==None 检查后各自 save，后者覆盖前者，
        同 key 并发返回不同 task_id 且产生孤儿任务。此方法把 check-and-set 收进单条
        INSERT ... ON CONFLICT DO NOTHING，凭 rowcount 判定抢占结果，无中间竞态窗口。
        注意：绕过 _enqueue_write 批量缓冲（调用方必须立即读到抢占结果）。
        """
        _, conn, conn_lock = await self._get_write_conn()
        async with conn_lock:
            cursor = await conn.execute(
                "INSERT INTO idempotency_keys (idempotency_key, task_id, created_at) VALUES (?, ?, ?)"
                " ON CONFLICT(idempotency_key) DO NOTHING",
                (key, task_id, time.time()),
            )
            if cursor.rowcount > 0:
                await conn.commit()
                self._commit_count += 1
                return task_id
            existing = await conn.execute(
                "SELECT task_id FROM idempotency_keys WHERE idempotency_key=?", (key,)
            )
            row = await existing.fetchone()
            await conn.commit()
            self._commit_count += 1
            if row:
                return str(row[0])
            # 理论不可达：rowcount==0 且 select 为空说明并发删除（clean_expired）竞态，
            # 保守回退为直接写入本 task_id
            await conn.execute(
                "INSERT INTO idempotency_keys (idempotency_key, task_id, created_at) VALUES (?, ?, ?)",
                (key, task_id, time.time()),
            )
            await conn.commit()
            self._commit_count += 1
            return task_id

    async def get_idempotency(self, key: str) -> dict | None:
        """查询幂等 key，返回 {idempotency_key, task_id, created_at} 或 None。"""
        await self._ensure_flushed()
        conn = await self._get_read_conn()
        cursor = await conn.execute(
            "SELECT idempotency_key, task_id, created_at FROM idempotency_keys WHERE idempotency_key=?", (key,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return dict(zip(row.keys(), row))

    async def clean_expired_idempotency(self) -> int:
        """清理超 TTL 的幂等 key 条目，返回删除数。"""
        cutoff = time.time() - config.IF_IDEMPOTENCY_TTL
        _, conn, conn_lock = await self._get_write_conn()
        async with conn_lock:
            cur = await conn.execute("DELETE FROM idempotency_keys WHERE created_at < ?", (cutoff,))
            await conn.commit()
            return cur.rowcount

    # ── IMP-21: 死信队列（DLQ）────────────────────────────
    async def push_dlq(self, task_id: str, model: str | None, error: str | None, attempts: int) -> None:
        """将重试耗尽的任务推入死信队列。"""
        now = time.time()
        await self._enqueue_write(
            "INSERT OR REPLACE INTO dead_letter_queue"
            " (id, task_id, model, error, attempts, created_at, last_attempt_at, raw_log)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, task_id, model, error, attempts, now, now, error),
        )

    async def list_dlq(self, limit: int = 20) -> list[dict]:
        """列出死信队列记录，按 created_at 降序。"""
        await self._ensure_flushed()
        conn = await self._get_read_conn()
        cursor = await conn.execute(
            "SELECT id, task_id, model, error, attempts, created_at, last_attempt_at, raw_log"
            " FROM dead_letter_queue ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(zip(row.keys(), row)) for row in rows]

    async def retry_dlq(self, task_id: str) -> None:
        """从死信队列移除指定任务（重试语义：删除记录，重新入队）。"""
        await self._enqueue_write("DELETE FROM dead_letter_queue WHERE id=?", (task_id,))

    async def clear_dlq(self) -> None:
        """清空死信队列所有记录。"""
        await self._enqueue_write("DELETE FROM dead_letter_queue", ())

    async def clean_expired_dlq(self) -> int:
        """清理超期死信队列记录，返回删除数。"""
        cutoff = time.time() - config.IF_DLQ_RETENTION_DAYS * 86400
        _, conn, conn_lock = await self._get_write_conn()
        async with conn_lock:
            cur = await conn.execute("DELETE FROM dead_letter_queue WHERE created_at < ?", (cutoff,))
            await conn.commit()
            return cur.rowcount

    # ── IMP-11: 缓存持久化 ─────────────────────────────
    async def save_cache_batch(self, entries: list[tuple[str, str, float]]) -> None:
        """批量写入缓存条目到 cache_store 表（upsert 语义）。"""
        if not entries:
            return
        now = time.time()
        _, conn, conn_lock = await self._get_write_conn()
        async with conn_lock:
            await conn.executemany(
                "INSERT OR REPLACE INTO cache_store (key, value, ttl, cached_at) VALUES (?, ?, ?, ?)",
                [(k, v, ttl, now) for k, v, ttl in entries],
            )
            await conn.commit()

    async def load_cache_snapshot(self) -> list[tuple[str, str, float]]:
        """从 cache_store 表读取所有未过期的缓存条目。"""
        await self._ensure_flushed()
        now = time.time()
        conn = await self._get_read_conn()
        cursor = await conn.execute("SELECT key, value, ttl, cached_at FROM cache_store")
        rows = await cursor.fetchall()
        result: list[tuple[str, str, float]] = []
        for row in rows:
            deadline = row["cached_at"] + row["ttl"]
            remaining = deadline - now
            if remaining > 0:
                result.append((row["key"], row["value"], remaining))
        return result

    async def delete_cache_batch(self, keys: list[str]) -> None:
        """批量删除指定缓存 key。"""
        if not keys:
            return
        _, conn, conn_lock = await self._get_write_conn()
        async with conn_lock:
            await conn.executemany("DELETE FROM cache_store WHERE key=?", [(k,) for k in keys])
            await conn.commit()

    async def clean_expired_cache(self) -> int:
        """清理过期缓存条目（TTL 到期），返回删除数。"""
        _, conn, conn_lock = await self._get_write_conn()
        async with conn_lock:
            cur = await conn.execute("DELETE FROM cache_store WHERE cached_at + ttl < ?", (time.time(),))
            await conn.commit()
            return cur.rowcount


# ── 旧同步实现（已废弃，保留仅为兼容）─────────────────────────────────────────


class QueueDB:
    """持久化队列 DB（同步实现，**已废弃**）。

    ⚠️ 此实现使用同步 sqlite3，会阻塞事件循环。
    请使用 `api.db.queue_store.QueueStore`（异步 aiosqlite）替代。

    保留仅为兼容已有引用，**不要在新代码中使用**。
    """

    def __init__(self, path: str):
        import sqlite3

        self._conn = sqlite3.connect(path, check_same_thread=False)
        # 极限性能调优参数（v5.2）：与主库一致的写读无锁并发 + 内存缓存
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._conn.execute("PRAGMA cache_size=-64000")  # 64MB
        self._conn.execute("PRAGMA mmap_size=268435456")  # 256MB
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS task_queue (
                    id          TEXT PRIMARY KEY,
                    priority    INT DEFAULT 2,
                    seq         INT,
                    created_at  REAL,
                    status      TEXT DEFAULT 'pending'
                );
                CREATE INDEX IF NOT EXISTS idx_queue_status ON task_queue(status);
                CREATE INDEX IF NOT EXISTS idx_queue_priority ON task_queue(priority, seq);
            """)
            self._conn.commit()

    def enqueue(self, task_id: str, priority: int, seq: int) -> None:
        """写入待消费队列。"""
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO task_queue (id, priority, seq, created_at, status)"
                " VALUES (?, ?, ?, ?, 'pending')",
                (task_id, priority, seq, time.time()),
            )
            self._conn.commit()

    def mark_processing(self, task_id: str) -> None:
        """标记为处理中。"""
        with self._lock:
            self._conn.execute("UPDATE task_queue SET status='processing' WHERE id=?", (task_id,))
            self._conn.commit()

    def mark_completed(self, task_id: str) -> None:
        """标记为已完成。"""
        with self._lock:
            self._conn.execute("UPDATE task_queue SET status='completed' WHERE id=?", (task_id,))
            self._conn.commit()

    def list_pending(self) -> list[tuple[int, int, str]]:
        """返回所有 pending 任务，按 priority/seq 升序。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT priority, seq, id FROM task_queue" " WHERE status='pending' ORDER BY priority, seq"
            ).fetchall()
            return [(r[0], r[1], r[2]) for r in rows]

    def cleanup(self, retention_days: int = 7) -> dict:
        """清理超期 completed/processing 记录，返回删除数。"""
        cutoff = time.time() - retention_days * 86400
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM task_queue WHERE status IN ('completed','processing') AND created_at < ?",
                (cutoff,),
            )
            self._conn.commit()
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            return {"deleted": cur.rowcount}

    def close(self) -> None:
        self._conn.close()


def task_to_public(t: dict) -> dict:
    """数据库行 → API 响应结构。"""
    from ..geo_ip import guess_country

    b64 = t.get("image_base64")
    if b64 and isinstance(b64, str) and b64.startswith("file://"):
        path = b64[7:]
        try:
            with open(path, encoding="utf-8") as f:
                b64 = f.read()
            if len(b64) > 10 * 1024 * 1024:
                log.warning("base64 文件超过 10MB 限制，跳过 task_to_public: %s", path)
                b64 = None
        except OSError:
            b64 = None

    ip = t.get("client_ip") or ""
    loc_info = guess_country(ip) if ip else None
    loc_str = f"{loc_info['emoji']} {loc_info['desc']}" if loc_info else "—"
    # 私网/回环/链路本地（LAN）：不回传原始 IP，防内网拓扑泄露被恶意者利用
    is_internal = bool(loc_info and loc_info.get("code") in ("LAN",))
    public_ip = "" if is_internal else (t.get("client_ip") or "")

    # 阶段耗时拆解（从 error / slow / duration 提炼）
    dur = t.get("duration_sec")
    timings = {}
    if dur is not None:
        timings["total_sec"] = round(dur, 2)

    return {
        "id": t["id"],
        "status": t["status"],
        "image_url": t["image_url"],
        "image_base64": b64,
        "image_mime": t.get("image_mime"),
        "error": t["error"],
        "created_at": t["created_at"],
        "duration_sec": t["duration_sec"],
        "type": t.get("type", "txt"),
        "model": t.get("model", "default"),
        "prompt": t.get("prompt"),
        "aspect_ratio": t.get("aspect_ratio"),
        "client_ip": public_ip or None,
        "client_location": loc_str,
        "user_agent": t.get("user_agent"),
        "timings": timings,
    }
