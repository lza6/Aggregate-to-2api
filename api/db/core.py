"""DB 类完整实现：连接管理/读写分离/批量写/查询/清理/幂等/DLQ/缓存持久化。"""
from __future__ import annotations

import asyncio
import atexit
import logging
import os
import time
import weakref

import aiosqlite

from .. import config
from .. import base64_store
from ..telemetry import get_tracer

log = logging.getLogger("db")

# 进程内所有 DB 实例（弱引用）+ 全部 aiosqlite 连接（强引用，直到显式 stop）。
_LIVE_DBS: weakref.WeakSet = weakref.WeakSet()
_LIVE_CONNS: list = []


def _force_stop_aiosqlite(conn) -> None:
    """loop 已死或不走 await close 时：关底层 sqlite + 停 aiosqlite 工作线程。"""
    try:
        raw = getattr(conn, "_connection", None)
        if raw is not None:
            raw.close()
    except Exception:
        pass
    stop = getattr(conn, "_stop_running", None)
    if stop is not None:
        try:
            stop()
        except Exception:
            pass


def _atexit_stop_db_threads() -> None:
    for db in list(_LIVE_DBS):
        try:
            db.stop_threads_now()
        except Exception:
            pass
    for conn in list(_LIVE_CONNS):
        _force_stop_aiosqlite(conn)
    _LIVE_CONNS.clear()


atexit.register(_atexit_stop_db_threads)


class BatchWrite:
    """写操作缓冲条目（IMP-25）。"""
    __slots__ = ("sql", "params")

    def __init__(self, sql: str, params: tuple):
        self.sql = sql
        self.params = params


class DB:
    def __init__(self, path: str):
        self._path = path
        self._pool_size = max(1, config.IF_DB_POOL_SIZE)

        # ── 读连接池（多连接，round-robin 分配，无需锁）──────────
        self._read_conns: list[aiosqlite.Connection] = []
        self._read_idx = 0
        # 向后兼容：旧代码测试访问 db._read_conn（初始化后为 _read_conns[0]）
        self._read_conn: aiosqlite.Connection | None = None

        # ── 写连接池 ─────────────────────────────────────
        self._connections: list[aiosqlite.Connection] = []
        self._conn_locks: list[asyncio.Lock] = []
        self._next_conn_idx = 0

        # 向后兼容：旧代码/direct 测试访问 db._conn
        self._conn: aiosqlite.Connection | None = None

        # ── 写缓冲区锁（仅保护 _write_buffer 的 swap 操作）───
        self._lock: asyncio.Lock | None = None

        # ── 批量写入（IMP-25）─────────────────────────────
        self._batch_enabled = config.IF_DB_BATCH_ENABLED
        self._batch_window = config.IF_DB_BATCH_WINDOW
        self._write_buffer: list[BatchWrite] = []
        self._batch_running = False
        self._commit_count = 0

        # 惰性初始化
        self._initialized = False
        self._pool_loop: asyncio.AbstractEventLoop | None = None
        _LIVE_DBS.add(self)

    def stop_threads_now(self) -> None:
        """同步停掉本实例全部 aiosqlite 线程（进程退出 / pytest sessionfinish 用）。"""
        for conn in list(self._connections) + list(self._read_conns):
            _force_stop_aiosqlite(conn)
        self._connections.clear()
        self._read_conns.clear()
        self._initialized = False
        self._lock = None

    def _get_lock(self) -> asyncio.Lock:
        """惰性获取写缓冲锁。"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def _init_async(self, pool_timeout: int) -> None:
        """异步初始化：创建所有连接并运行 schema。"""
        if self._initialized:
            return
        for _ in range(self._pool_size):
            conn = await self._create_conn(self._path, pool_timeout)
            self._read_conns.append(conn)
        self._read_conn = self._read_conns[0]
        for _ in range(self._pool_size):
            conn = await self._create_conn(self._path, pool_timeout)
            self._connections.append(conn)
            self._conn_locks.append(asyncio.Lock())
        self._conn = self._connections[0]
        await self._init_schema()
        self._initialized = True
        try:
            self._pool_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._pool_loop = None

    async def _ensure_initialized(self) -> None:
        """确保连接已初始化（惰性初始化，用于 async 上下文中的 __init__）。"""
        cur_loop = asyncio.get_running_loop()
        if self._initialized:
            if self._pool_loop is not cur_loop:
                await self._rebuild_for_loop(cur_loop)
            return
        await self._init_async(config.IF_DB_POOL_TIMEOUT)
        self._pool_loop = cur_loop

    async def _rebuild_for_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """当前 loop 与连接池绑定 loop 不一致：关旧连接、在新 loop 重建。"""
        log.warning("DB 连接池 loop 漂移（%s → %s），重建连接池",
                    self._pool_loop, loop)
        old_loop = self._pool_loop
        old_alive = old_loop is not None and not old_loop.is_closed()
        for conn in (*self._connections, *self._read_conns):
            try:
                if old_alive:
                    await conn.close()
                else:
                    raw_conn = getattr(conn, "_connection", None)
                    if raw_conn is not None:
                        raw_conn.close()
                    conn._stop_running()
            except Exception:
                pass
        self._connections.clear()
        self._read_conns.clear()
        self._conn_locks.clear()
        self._initialized = False
        self._lock = None
        await self._init_async(config.IF_DB_POOL_TIMEOUT)
        self._pool_loop = loop

    # ── 连接管理 ─────────────────────────────────────

    @staticmethod
    async def _create_conn(path: str, timeout: int = 5) -> aiosqlite.Connection:
        """创建一条 aiosqlite 连接（WAL + NORMAL + busy_timeout + autocommit）。"""
        conn = await aiosqlite.connect(path, timeout=timeout, isolation_level=None)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA busy_timeout=10000")
        await conn.execute("PRAGMA cache_size=-64000")      # 64MB 页缓存
        await conn.execute("PRAGMA mmap_size=268435456")    # 256MB 内存映射 I/O
        await conn.execute("PRAGMA temp_store=MEMORY")
        await conn.execute("PRAGMA wal_autocheckpoint=1000")
        _LIVE_CONNS.append(conn)
        return conn

    async def _health_check(self, conn: aiosqlite.Connection) -> bool:
        """健康检查：PRAGMA quick_check，返回 True 表示正常。"""
        try:
            cursor = await conn.execute("PRAGMA quick_check")
            row = await cursor.fetchone()
            return row[0] == "ok"
        except Exception:
            return False

    async def _reconnect(self, idx: int) -> aiosqlite.Connection:
        """重建 idx 位置的写连接，返回新连接。"""
        try:
            await self._connections[idx].close()
        except Exception:
            pass
        new_conn = await self._create_conn(self._path, config.IF_DB_POOL_TIMEOUT)
        self._connections[idx] = new_conn
        if idx == 0:
            self._conn = new_conn
        return new_conn

    async def _reconnect_read(self, idx: int) -> aiosqlite.Connection:
        """重建 idx 位置的读连接，返回新连接。"""
        try:
            await self._read_conns[idx].close()
        except Exception:
            pass
        new_conn = await self._create_conn(self._path, config.IF_DB_POOL_TIMEOUT)
        self._read_conns[idx] = new_conn
        return new_conn

    async def _get_write_conn(self) -> tuple[int, aiosqlite.Connection, asyncio.Lock]:
        """Round-robin 分配写连接，返回 (idx, conn, lock)。"""
        await self._ensure_initialized()
        idx = self._next_conn_idx
        self._next_conn_idx = (idx + 1) % self._pool_size
        conn = self._connections[idx]
        lock = self._conn_locks[idx]
        if not await self._health_check(conn):
            log.warning("DB 写连接[%d] 健康检查失败，重建", idx)
            conn = await self._reconnect(idx)
        return idx, conn, lock

    async def _get_read_conn(self) -> aiosqlite.Connection:
        """Round-robin 分配读连接。"""
        await self._ensure_initialized()
        idx = self._read_idx
        self._read_idx = (idx + 1) % self._pool_size
        conn = self._read_conns[idx]
        if not await self._health_check(conn):
            log.warning("DB 读连接[%d] 健康检查失败，重建", idx)
            conn = await self._reconnect_read(idx)
        return conn

    async def close(self) -> None:
        """关闭所有连接（写连接池 + 读连接池）。"""
        for conn in list(self._connections) + list(self._read_conns):
            try:
                await conn.close()
            except Exception:
                _force_stop_aiosqlite(conn)
        self._connections.clear()
        self._read_conns.clear()
        self._initialized = False

    # ── 批量写入 API ─────────────────────────────────
    async def _enqueue_write(self, sql: str, params: tuple) -> None:
        """批量模式：入队写操作；非批量模式：立即执行并 commit。"""
        if not self._batch_enabled:
            _, conn, conn_lock = await self._get_write_conn()
            async with conn_lock:
                await conn.execute(sql, params)
                await conn.commit()
                self._commit_count += 1
            return
        self._write_buffer.append(BatchWrite(sql, params))

    async def _flush_buffer(self) -> None:
        """批量执行缓冲区所有 SQL 并 commit（需在 _lock 内调用）。"""
        if not self._write_buffer:
            return
        buf, self._write_buffer = self._write_buffer, []
        _, conn, conn_lock = await self._get_write_conn()
        async with conn_lock:
            for bw in buf:
                await conn.execute(bw.sql, bw.params)
            await conn.commit()
            self._commit_count += 1

    async def flush(self) -> None:
        """公开方法：强制刷新缓冲区到 DB（stop 时调用确保数据不丢）。"""
        if not self._batch_enabled:
            return
        async with self._get_lock():
            await self._flush_buffer()

    async def start_batch_timer(self) -> None:
        """后台协程：每 batch_window 秒触发一次 flush。"""
        if not self._batch_enabled:
            return
        self._batch_running = True
        try:
            while self._batch_running:
                await asyncio.sleep(self._batch_window)
                async with self._get_lock():
                    await self._flush_buffer()
        except asyncio.CancelledError:
            async with self._get_lock():
                await self._flush_buffer()
            raise

    def stop_batch_timer(self) -> None:
        self._batch_running = False

    # ── 读前自动 flush ──
    async def _ensure_flushed(self) -> None:
        """批量写入模式下，读操作前刷新缓冲区，确保数据可见性。"""
        await self._ensure_initialized()
        if self._batch_enabled:
            async with self._get_lock():
                await self._flush_buffer()

    # ── 结构 ──────────────────────────────────────
    async def _init_schema(self) -> None:
        conn = self._connections[0]
        conn_lock = self._conn_locks[0]
        async with conn_lock:
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
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    idempotency_key TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    created_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_idempotency_created ON idempotency_keys(created_at);
            """)
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
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS cache_store (
                    key         TEXT PRIMARY KEY,
                    value       TEXT NOT NULL,
                    ttl         REAL NOT NULL,
                    cached_at   REAL NOT NULL
                );
            """)
            cursor = await conn.execute("PRAGMA table_info(requests)")
            rows = await cursor.fetchall()
            cols = {r[1] for r in rows}
            for col, ddl in (("image_base64", "TEXT"), ("image_mime", "TEXT"),
                             ("type", "TEXT DEFAULT 'txt'"), ("model", "TEXT DEFAULT 'default'"),
                             ("upstream_task_id", "TEXT"),
                             ("day", "TEXT"), ("month", "TEXT"),
                             ("proxy_used", "TEXT")):
                if col not in cols:
                    await conn.execute(f"ALTER TABLE requests ADD COLUMN {col} {ddl}")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_created_status ON requests(created_at, status)")
            await conn.commit()

    # ── 写 ────────────────────────────────────────
    async def create_request(self, task_id: str, prompt: str, aspect_ratio: str, download: bool,
                             type_: str = "txt", model: str = "default") -> None:
        tracer = get_tracer()
        with tracer.start_as_current_span(
            "db.create_request",
            attributes={"task.id": task_id, "task.type": type_, "task.model": model, "task.aspect_ratio": aspect_ratio},
        ):
            now = time.time()
            import datetime
            dt = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc)
            day = dt.strftime("%Y-%m-%d")
            month = dt.strftime("%Y-%m")
            await self._enqueue_write(
                "INSERT INTO requests (id, prompt, aspect_ratio, download, status, created_at, type, model, day, month)"
                " VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)",
                (task_id, prompt, aspect_ratio, int(download), now, type_, model, day, month),
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

    async def mark_finished(self, task_id: str, status: str, image_url: str | None,
                            error: str | None, duration_sec: float | None,
                            image_base64: str | None = None, image_mime: str | None = None) -> None:
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
                (status, image_url, image_base64, image_mime, error, time.time(),
                 duration_sec, task_id),
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

    async def recover_stale_tasks(self, reason: str = "服务重启，任务中断",
                                   stale_after: float = 300.0) -> int:
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
        "id", "status", "image_url", "image_base64", "image_mime", "error",
        "created_at", "duration_sec", "type", "model",
    )
    _TASK_LIST_COLS = (
        "id", "status", "image_url", "error",
        "created_at", "duration_sec", "type", "model", "aspect_ratio",
    )
    _GALLERY_COLS = (
        "id", "status", "image_url", "image_mime", "error",
        "created_at", "finished_at", "duration_sec", "type", "model",
        "prompt", "aspect_ratio",
    )
    _ERROR_COLS = (
        "id", "status", "error",
        "created_at", "duration_sec", "type", "model",
        "prompt", "aspect_ratio",
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

    async def list_tasks(self, limit: int = 50, offset: int = 0,
                          status: str | None = None, model: str | None = None,
                          sort: str = "created_at") -> tuple[list[dict], int]:
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
            " ORDER BY finished_at DESC LIMIT ?", (limit,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def recent_errors(self, limit: int = 20) -> list[dict]:
        """最近失败的请求（含错误原因/prompt），供在线排查。"""
        await self._ensure_flushed()
        cols = ", ".join(self._ERROR_COLS)
        conn = await self._get_read_conn()
        cursor = await conn.execute(
            f"SELECT {cols} FROM requests WHERE status='error'"
            " ORDER BY created_at DESC LIMIT ?", (limit,),
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
            " GROUP BY day ORDER BY day", (cutoff,),
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
            " GROUP BY month ORDER BY month", (cutoff,),
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
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM requests WHERE created_at >= ?", (cutoff,)
        )
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
            "INSERT OR REPLACE INTO idempotency_keys (idempotency_key, task_id, created_at)"
            " VALUES (?, ?, ?)", (key, task_id, time.time()),
        )

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
            " FROM dead_letter_queue ORDER BY created_at DESC LIMIT ?", (limit,),
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