"""SQLite 持久化：请求记录、按日/月统计、画廊、并发计数。

选 SQLite（标准库，WAL 模式）而非 JSON：50 RPS 高频写 + 并发读下，
JSON 整文件重写有锁竞争；SQLite 单行 INSERT 毫秒级，WAL 支持读写并行。

IMP-20: 多连接支持。写连接池（round-robin 分配），读连接独立（WAL 快照隔离）。
写入用连接级锁串行化，读不加锁。

IMP-25: 写缓冲 + 批量提交。当 IF_DB_BATCH_ENABLED=1 时，写操作先入队
_write_buffer，后台 _batch_timer 每 batch_window 秒触发一次 flush，
将收集的 SQL 批量执行 + 一次 commit，减少 50 RPS 下每任务 2 次 commit 的
频繁提交压力。BATCH_ENABLED=0 时保持原行为（立即 execute+commit）。

时间戳用 Unix 秒（UTC）；日/月分组用 'localtime' 适配服务器本地时区。
"""
import asyncio
import logging
import os
import sqlite3
import threading
import time

from . import config
from . import base64_store

log = logging.getLogger("db")


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
        pool_timeout = config.IF_DB_POOL_TIMEOUT

        # ── 读连接（单连接，WAL 快照隔离，无需加锁）───────────
        self._read_conn = self._create_conn(path, pool_timeout)

        # ── 写连接池 ─────────────────────────────────────
        self._connections: list[sqlite3.Connection] = []
        self._conn_locks: list[threading.Lock] = []
        for _ in range(self._pool_size):
            conn = self._create_conn(path, pool_timeout)
            self._connections.append(conn)
            self._conn_locks.append(threading.Lock())
        self._next_conn_idx = 0

        # 向后兼容：旧代码/direct 测试访问 db._conn
        self._conn = self._connections[0]

        # ── 写缓冲区锁（仅保护 _write_buffer，非连接级）───
        self._lock = threading.Lock()

        # ── 批量写入（IMP-25）─────────────────────────────
        self._batch_enabled = config.IF_DB_BATCH_ENABLED
        self._batch_window = config.IF_DB_BATCH_WINDOW
        self._write_buffer: list[BatchWrite] = []
        self._batch_running = False
        self._commit_count = 0  # 调试计数器，仅在 _flush_buffer 中递增

        self._init_schema()

    # ── 连接管理 ─────────────────────────────────────

    @staticmethod
    def _create_conn(path: str, timeout: int = 5) -> sqlite3.Connection:
        """创建一条 SQLite 连接（WAL + NORMAL + busy_timeout + 跨线程安全）。"""
        conn = sqlite3.connect(path, timeout=timeout, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA wal_autocheckpoint=1000")
        return conn

    def _health_check(self, conn: sqlite3.Connection) -> bool:
        """健康检查：PRAGMA quick_check，返回 True 表示正常。"""
        try:
            result = conn.execute("PRAGMA quick_check").fetchone()[0]
            return result == "ok"
        except Exception:
            return False

    def _reconnect(self, idx: int) -> sqlite3.Connection:
        """重建 idx 位置的写连接，返回新连接。"""
        try:
            self._connections[idx].close()
        except Exception:
            pass
        new_conn = self._create_conn(self._path, config.IF_DB_POOL_TIMEOUT)
        self._connections[idx] = new_conn
        if idx == 0:
            self._conn = new_conn
        return new_conn

    def _get_write_conn(self) -> tuple[int, sqlite3.Connection, threading.Lock]:
        """Round-robin 分配写连接，返回 (idx, conn, lock)。

        分配前执行健康检查，失效则自动重建。
        """
        idx = self._next_conn_idx
        self._next_conn_idx = (idx + 1) % self._pool_size
        conn = self._connections[idx]
        lock = self._conn_locks[idx]
        if not self._health_check(conn):
            log.warning("DB 写连接[%d] 健康检查失败，重建", idx)
            conn = self._reconnect(idx)
        return idx, conn, lock

    def close(self) -> None:
        """关闭所有连接（写连接池 + 读连接）。"""
        for conn in self._connections:
            try:
                conn.close()
            except Exception:
                pass
        try:
            self._read_conn.close()
        except Exception:
            pass

    # ── 批量写入 API ─────────────────────────────────
    def _enqueue_write(self, sql: str, params: tuple) -> None:
        """批量模式：入队写操作；非批量模式：立即执行并 commit。"""
        if not self._batch_enabled:
            _, conn, conn_lock = self._get_write_conn()
            with conn_lock:
                conn.execute(sql, params)
                conn.commit()
                self._commit_count += 1
            return
        with self._lock:
            self._write_buffer.append(BatchWrite(sql, params))

    def _flush_buffer(self) -> None:
        """批量执行缓冲区所有 SQL 并 commit（需在 _lock 内调用）。"""
        if not self._write_buffer:
            return
        buf, self._write_buffer = self._write_buffer, []
        _, conn, conn_lock = self._get_write_conn()
        with conn_lock:
            for bw in buf:
                conn.execute(bw.sql, bw.params)
            conn.commit()
            self._commit_count += 1

    def flush(self) -> None:
        """公开方法：强制刷新缓冲区到 DB（stop 时调用确保数据不丢）。"""
        if not self._batch_enabled:
            return
        with self._lock:
            self._flush_buffer()

    async def start_batch_timer(self) -> None:
        """后台协程：每 batch_window 秒触发一次 flush。"""
        if not self._batch_enabled:
            return
        self._batch_running = True
        try:
            while self._batch_running:
                await asyncio.sleep(self._batch_window)
                with self._lock:
                    self._flush_buffer()
        except asyncio.CancelledError:
            with self._lock:
                self._flush_buffer()
            raise

    def stop_batch_timer(self) -> None:
        self._batch_running = False

    # ── 读前自动 flush（IMP-25：批量模式下，读操作前刷新缓冲区确保数据可见）──
    def _ensure_flushed(self) -> None:
        """批量写入模式下，读操作前刷新缓冲区，确保数据可见性。"""
        if self._batch_enabled and self._write_buffer:
            with self._lock:
                self._flush_buffer()

    # ── 结构 ──────────────────────────────────────
    def _init_schema(self) -> None:
        conn = self._connections[0]
        with self._conn_locks[0]:
            conn.executescript(
                """
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
                """
            )
            # IMP-06: idempotency_keys 表
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    idempotency_key TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    created_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_idempotency_created ON idempotency_keys(created_at);
                """
            )
            # IMP-21: dead_letter_queue 表
            conn.executescript(
                """
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
                """
            )
            # IMP-11: 缓存持久化表
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cache_store (
                    key         TEXT PRIMARY KEY,
                    value       TEXT NOT NULL,
                    ttl         REAL NOT NULL,
                    cached_at   REAL NOT NULL
                );
                """
            )
            # IMP-07: 复合索引 + day/month 列
            cols = {r[1] for r in conn.execute("PRAGMA table_info(requests)")}
            for col, ddl in (("image_base64", "TEXT"), ("image_mime", "TEXT"),
                             ("type", "TEXT DEFAULT 'txt'"), ("model", "TEXT DEFAULT 'default'"),
                             ("upstream_task_id", "TEXT"),
                             ("day", "TEXT"), ("month", "TEXT"),
                             ("proxy_used", "TEXT")):
                if col not in cols:
                    conn.execute(f"ALTER TABLE requests ADD COLUMN {col} {ddl}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_created_status ON requests(created_at, status)")
            conn.commit()

    # ── 写 ────────────────────────────────────────
    def create_request(self, task_id: str, prompt: str, aspect_ratio: str, download: bool,
                       type_: str = "txt", model: str = "default") -> None:
        now = time.time()
        # 预计算 day/month 列（IMP-07）
        import datetime
        dt = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc)
        day = dt.strftime("%Y-%m-%d")
        month = dt.strftime("%Y-%m")
        self._enqueue_write(
            "INSERT INTO requests (id, prompt, aspect_ratio, download, status, created_at, type, model, day, month)"
            " VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)",
            (task_id, prompt, aspect_ratio, int(download), now, type_, model, day, month),
        )

    def mark_started(self, task_id: str) -> None:
        self._enqueue_write(
            "UPDATE requests SET status='processing', started_at=? WHERE id=?",
            (time.time(), task_id),
        )

    def mark_finished(self, task_id: str, status: str, image_url: str | None,
                      error: str | None, duration_sec: float | None,
                      image_base64: str | None = None, image_mime: str | None = None) -> None:
        # IMP-26: base64 非空时写入文件缓存，DB 存 file:// 路径
        if image_base64 and image_mime:
            image_base64 = base64_store.save_base64(task_id, image_base64, image_mime)
        self._enqueue_write(
            "UPDATE requests SET status=?, image_url=?, image_base64=?, image_mime=?,"
            " error=?, finished_at=?, duration_sec=? WHERE id=?",
            (status, image_url, image_base64, image_mime, error, time.time(),
             duration_sec, task_id),
        )

    def update_upstream_task(self, task_id: str, upstream_task_id: str) -> None:
        """记录上游生成任务 id（图生图/文生图均可），便于恢复孤儿槽位与排查。"""
        self._enqueue_write(
            "UPDATE requests SET upstream_task_id=? WHERE id=?",
            (upstream_task_id, task_id),
        )

    def update_proxy_used(self, task_id: str, proxy: str | None) -> None:
        """记录该任务使用的出口代理（aifreeforever 等每请求轮换代理的提供商）。"""
        if proxy is not None:
            self._enqueue_write(
                "UPDATE requests SET proxy_used=? WHERE id=?",
                (proxy, task_id),
            )

    def recover_stale_tasks(self, reason: str = "服务重启，任务中断",
                            stale_after: float = 300.0) -> int:
        """启动时回收上次进程遗留的 pending/processing 孤儿任务（H4）。

        新进程内存队列为空，此刻 DB 里所有 pending/processing 都来自崩溃/重启前的旧进程，
        永远不会再被消费，标记为 error 防止统计失真、防止前端永久 pending。
        stale_after 时间门槛：只回收创建超过该秒数的陈旧任务，避免多进程部署下
        误伤其它进程刚入队/正在处理的任务（MEDIUM-2）。
        """
        cutoff = time.time() - stale_after
        _, conn, conn_lock = self._get_write_conn()
        with conn_lock:
            cur = conn.execute(
                "UPDATE requests SET status='error', error=?, finished_at=? "
                "WHERE status IN ('pending','processing') AND created_at < ?",
                (reason, time.time(), cutoff),
            )
            conn.commit()
            return cur.rowcount

    # ── 读 ────────────────────────────────────────
    _PUBLIC_COLS = (
        "id", "status", "image_url", "image_base64", "image_mime", "error",
        "created_at", "duration_sec", "type", "model",
    )

    # 任务列表列（不含 image_base64 大字段，避免批量文件解析 I/O）
    _TASK_LIST_COLS = (
        "id", "status", "image_url", "error",
        "created_at", "duration_sec", "type", "model", "aspect_ratio",
    )

    # 画廊/错误列表列（不含 base64 大字段，IMP-26）
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

    def get(self, task_id: str) -> dict | None:
        self._ensure_flushed()
        row = self._read_conn.execute(
            "SELECT * FROM requests WHERE id=?", (task_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    def get_public(self, task_id: str) -> dict | None:
        """轻量查询：只取公共 API 响应字段（不含 prompt），供 /v1/tasks 等读路径。"""
        self._ensure_flushed()
        cols = ", ".join(self._PUBLIC_COLS)
        row = self._read_conn.execute(
            f"SELECT {cols} FROM requests WHERE id=?", (task_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_dict(row, default=False)

    def list_tasks(self, limit: int = 50, offset: int = 0,
                   status: str | None = None, model: str | None = None,
                   sort: str = "created_at") -> tuple[list[dict], int]:
        """任务列表查询（IMP-41）。"""
        self._ensure_flushed()
        where = []
        params: list = []
        if status:
            where.append("status=?")
            params.append(status)
        if model:
            where.append("model=?")
            params.append(model)
        where_clause = (" WHERE " + " AND ".join(where)) if where else ""
        # 总条数
        total_row = self._read_conn.execute(
            f"SELECT COUNT(*) FROM requests{where_clause}", params
        ).fetchone()
        total = int(total_row[0])
        # 排序方向 — 白名单校验防止 SQL 注入
        allowed_sort = {"created_at", "duration_sec", "finished_at", "status", "model"}
        if sort not in allowed_sort:
            sort = "created_at"
        direction = "DESC" if sort in ("created_at", "finished_at") else "ASC"
        # 数据行
        cols = ", ".join(self._TASK_LIST_COLS)
        rows = self._read_conn.execute(
            f"SELECT {cols} FROM requests{where_clause}"
            f" ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        items = [self._row_to_dict(r) for r in rows]
        return items, total

    def recent_images(self, limit: int = 50) -> list[dict]:
        """画廊：最近完成的、有图的请求（IMP-26: 不含 image_base64）。"""
        self._ensure_flushed()
        cols = ", ".join(self._GALLERY_COLS)
        rows = self._read_conn.execute(
            f"SELECT {cols} FROM requests WHERE status='completed' AND image_url IS NOT NULL"
            " ORDER BY finished_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def recent_errors(self, limit: int = 20) -> list[dict]:
        """最近失败的请求（含错误原因/prompt），供在线排查，无需 SSH。
        IMP-26: 不含 image_base64。
        """
        self._ensure_flushed()
        cols = ", ".join(self._ERROR_COLS)
        rows = self._read_conn.execute(
            f"SELECT {cols} FROM requests WHERE status='error'"
            " ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ── 统计 ──────────────────────────────────────
    def stats_overview(self) -> dict:
        """总量 + 平均出图耗时。"""
        self._ensure_flushed()
        row = self._read_conn.execute(
            "SELECT COUNT(*) AS total, "
            " SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS images, "
            " SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors, "
            " AVG(CASE WHEN status='completed' AND duration_sec IS NOT NULL"
            "         THEN duration_sec END) AS avg_duration"
            " FROM requests"
        ).fetchone()
        total, images, errors, avg_duration = row
        return {
            "total_requests": int(total or 0),
            "total_images": int(images or 0),
            "total_errors": int(errors or 0),
            "avg_duration_sec": round(float(avg_duration), 1) if avg_duration else None,
        }

    def stats_daily(self, days: int = 14) -> list[dict]:
        """近 N 天：每天请求/出图/失败（IMP-07: 直接用 day 列）。"""
        self._ensure_flushed()
        import datetime
        cutoff_dt = datetime.date.today() - datetime.timedelta(days=days)
        cutoff = cutoff_dt.strftime("%Y-%m-%d")
        rows = self._read_conn.execute(
            "SELECT day, COUNT(*) AS total, "
            " SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS images, "
            " SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors"
            " FROM requests WHERE day >= ?"
            " GROUP BY day ORDER BY day",
            (cutoff,),
        ).fetchall()
        return [{"day": r[0], "total": r[1], "images": r[2], "errors": r[3]} for r in rows]

    def stats_monthly(self, months: int = 12) -> list[dict]:
        """近 N 月：每月请求/出图/失败（IMP-07: 直接用 month 列）。"""
        self._ensure_flushed()
        import datetime
        now = datetime.date.today()
        # 取 months 月前的年-月
        y, m = now.year, now.month
        for _ in range(months):
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        cutoff = f"{y:04d}-{m:02d}"
        rows = self._read_conn.execute(
            "SELECT month, COUNT(*) AS total, "
            " SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS images, "
            " SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors"
            " FROM requests WHERE month >= ?"
            " GROUP BY month ORDER BY month",
            (cutoff,),
        ).fetchall()
        return [{"month": r[0], "total": r[1], "images": r[2], "errors": r[3]} for r in rows]

    # ── 增长治理（M7）──────────────────────────────
    def cleanup(self, retention_days: int) -> dict:
        """TTL 清理：删除超期请求记录，回收 WAL 并 VACUUM 压缩文件。"""
        self._ensure_flushed()
        cutoff = time.time() - retention_days * 86400
        # 取任一写连接的数据库路径
        path = self._connections[0].execute(
            "PRAGMA database_list"
        ).fetchone()[2]
        size_before = os.path.getsize(path) if os.path.exists(path) else 0
        _, conn, conn_lock = self._get_write_conn()
        with conn_lock:
            cur = conn.execute(
                "DELETE FROM requests WHERE created_at < ?", (cutoff,))
            conn.commit()
            deleted = cur.rowcount
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("VACUUM")
            except sqlite3.OperationalError as e:
                log.warning("VACUUM 失败（可忽略，稍后自动重试）: %s", e)
            conn.commit()
            # IMP-07: cleanup 后触发 ANALYZE 更新查询计划
            try:
                conn.execute("ANALYZE")
            except sqlite3.OperationalError:
                pass
        size_after = os.path.getsize(path) if os.path.exists(path) else 0
        return {"deleted": deleted, "size_before": size_before, "size_after": size_after}

    def count(self) -> int:
        """总记录数（指标用）。"""
        self._ensure_flushed()
        return int(self._read_conn.execute(
            "SELECT COUNT(*) FROM requests"
        ).fetchone()[0])

    @staticmethod
    def _row_to_dict(row: sqlite3.Row, default: bool = True) -> dict:
        keys = row.keys()
        d = dict(zip(keys, row))
        if "download" in d:
            d["download"] = bool(d["download"])
        d["duration_sec"] = round(d["duration_sec"], 1) if d.get("duration_sec") is not None else None
        d.setdefault("type", "txt")
        d.setdefault("model", "default")
        d.setdefault("upstream_task_id", None)
        # IMP-26: file:// 路径 → 读取文件内容还原 base64（向后兼容旧 raw base64）
        # P1: 限制最大 10MB 防 OOM
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
    def get_base64_path(self, task_id: str) -> str | None:
        """返回 task_id 对应的 base64 文件路径（file:// 前缀剥离），无文件时返回 None。"""
        self._ensure_flushed()
        row = self._read_conn.execute(
            "SELECT image_base64 FROM requests WHERE id=?", (task_id,)
        ).fetchone()
        if not row or not row[0]:
            return None
        val = str(row[0])
        if val.startswith("file://"):
            return val[7:]
        # 旧 raw base64 数据：无文件路径
        return None

    def read_base64(self, task_id: str) -> str | None:
        """从文件读取 task_id 的 base64 字符串。返回 None 表示文件不存在或读取失败。
        P1: 限制最大 10MB 防 OOM。"""
        path = self.get_base64_path(task_id)
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
    def save_idempotency(self, key: str, task_id: str) -> None:
        """保存幂等 key → task_id 映射。"""
        self._enqueue_write(
            "INSERT OR REPLACE INTO idempotency_keys (idempotency_key, task_id, created_at)"
            " VALUES (?, ?, ?)",
            (key, task_id, time.time()),
        )

    def get_idempotency(self, key: str) -> dict | None:
        """查询幂等 key，返回 {idempotency_key, task_id, created_at} 或 None。"""
        self._ensure_flushed()
        row = self._read_conn.execute(
            "SELECT idempotency_key, task_id, created_at FROM idempotency_keys"
            " WHERE idempotency_key=?", (key,)
        ).fetchone()
        if not row:
            return None
        return dict(zip(row.keys(), row))

    def clean_expired_idempotency(self) -> int:
        """清理超 TTL 的幂等 key 条目，返回删除数。"""
        cutoff = time.time() - config.IF_IDEMPOTENCY_TTL
        _, conn, conn_lock = self._get_write_conn()
        with conn_lock:
            cur = conn.execute(
                "DELETE FROM idempotency_keys WHERE created_at < ?", (cutoff,))
            conn.commit()
            return cur.rowcount

    # ── IMP-21: 死信队列（DLQ）────────────────────────────
    def push_dlq(self, task_id: str, model: str | None, error: str | None, attempts: int) -> None:
        """将重试耗尽的任务推入死信队列。"""
        now = time.time()
        self._enqueue_write(
            "INSERT OR REPLACE INTO dead_letter_queue"
            " (id, task_id, model, error, attempts, created_at, last_attempt_at, raw_log)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, task_id, model, error, attempts, now, now, error),
        )

    def list_dlq(self, limit: int = 20) -> list[dict]:
        """列出死信队列记录，按 created_at 降序（最新在前）。

        返回: [{id, task_id, model, error, attempts, created_at, last_attempt_at, raw_log}]
        """
        self._ensure_flushed()
        rows = self._read_conn.execute(
            "SELECT id, task_id, model, error, attempts, created_at, last_attempt_at, raw_log"
            " FROM dead_letter_queue ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(zip(row.keys(), row)) for row in rows]

    def retry_dlq(self, task_id: str) -> None:
        """从死信队列移除指定任务（重试语义：删除记录，重新入队）。"""
        self._enqueue_write(
            "DELETE FROM dead_letter_queue WHERE id=?", (task_id,),
        )

    def clear_dlq(self) -> None:
        """清空死信队列所有记录。"""
        self._enqueue_write(
            "DELETE FROM dead_letter_queue", (),
        )

    def clean_expired_dlq(self) -> int:
        """清理超期死信队列记录，返回删除数。"""
        cutoff = time.time() - config.IF_DLQ_RETENTION_DAYS * 86400
        _, conn, conn_lock = self._get_write_conn()
        with conn_lock:
            cur = conn.execute(
                "DELETE FROM dead_letter_queue WHERE created_at < ?", (cutoff,))
            conn.commit()
            return cur.rowcount

    # ── IMP-11: 缓存持久化 ─────────────────────────────
    def save_cache_batch(self, entries: list[tuple[str, str, float]]) -> None:
        """批量写入缓存条目到 cache_store 表（upsert 语义）。
        entries: [(key, json_value, remaining_ttl), ...]
        """
        if not entries:
            return
        now = time.time()
        _, conn, conn_lock = self._get_write_conn()
        with conn_lock:
            conn.executemany(
                "INSERT OR REPLACE INTO cache_store (key, value, ttl, cached_at)"
                " VALUES (?, ?, ?, ?)",
                [(k, v, ttl, now) for k, v, ttl in entries],
            )
            conn.commit()

    def load_cache_snapshot(self) -> list[tuple[str, str, float]]:
        """从 cache_store 表读取所有未过期的缓存条目。
        返回: [(key, value_json, remaining_ttl), ...]
        """
        self._ensure_flushed()
        now = time.time()
        rows = self._read_conn.execute(
            "SELECT key, value, ttl, cached_at FROM cache_store"
        ).fetchall()
        result: list[tuple[str, str, float]] = []
        for row in rows:
            deadline = row["cached_at"] + row["ttl"]
            remaining = deadline - now
            if remaining > 0:
                result.append((row["key"], row["value"], remaining))
        return result

    def delete_cache_batch(self, keys: list[str]) -> None:
        """批量删除指定缓存 key。"""
        if not keys:
            return
        _, conn, conn_lock = self._get_write_conn()
        with conn_lock:
            conn.executemany(
                "DELETE FROM cache_store WHERE key=?", [(k,) for k in keys],
            )
            conn.commit()

    def clean_expired_cache(self) -> int:
        """清理过期缓存条目（TTL 到期），返回删除数。"""
        _, conn, conn_lock = self._get_write_conn()
        with conn_lock:
            cur = conn.execute(
                "DELETE FROM cache_store WHERE cached_at + ttl < ?", (time.time(),))
            conn.commit()
            return cur.rowcount


class QueueDB:
    """持久化队列 DB（IMP-29）：独立 SQLite 文件，记录待消费任务。

    重启后从未消费的 task_queue 中恢复任务，避免重启丢失队列。
    """

    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
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
            self._conn.execute(
                "UPDATE task_queue SET status='processing' WHERE id=?", (task_id,))
            self._conn.commit()

    def mark_completed(self, task_id: str) -> None:
        """标记为已完成。"""
        with self._lock:
            self._conn.execute(
                "UPDATE task_queue SET status='completed' WHERE id=?", (task_id,))
            self._conn.commit()

    def list_pending(self) -> list[tuple[int, int, str]]:
        """返回所有 pending 任务，按 priority/seq 升序。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT priority, seq, id FROM task_queue"
                " WHERE status='pending' ORDER BY priority, seq"
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
            except sqlite3.OperationalError:
                pass
            return {"deleted": cur.rowcount}

    def close(self) -> None:
        self._conn.close()


def task_to_public(t: dict) -> dict:
    """数据库行 → API 响应结构。"""
    # IMP-26: file:// 路径 → 读取文件内容还原 base64
    # P1: 限制最大 10MB 防 OOM
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
    }