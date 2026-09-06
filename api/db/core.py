"""DB 连接池 + WAL checkpoint + 批量写基础设施。

P0-F3 拆分后职责边界：
- **core.py**（本文件）：连接池（读/写双池 round-robin + 健康检查 + 自动重建）、
  WAL 定期 checkpoint、批量写缓冲区（IMP-25）、schema 初始化委托。
- **queries.py**：``DBQueriesMixin`` —— DB 类的全部业务查询/写入/清理/幂等/DLQ/缓存
  持久化方法。``DB`` 继承本 mixin 获得这些方法，旧 ``from api.db.core import DB``
  零感知。
- **migrations.py**：所有 CREATE TABLE / CREATE INDEX / ALTER TABLE 兼容迁移 DDL。

公共接口（不动）：
- ``from api.db.core import DB, BatchWrite``
- ``DB`` 实例方法（create_request / get / claim_idempotency / push_dlq / ...）签名不变。
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import weakref

import aiosqlite

from .. import config
from .queries import DBQueriesMixin

log = logging.getLogger("db")

# WAL 定期 checkpoint 间隔（秒）：P1-L 每 5 分钟回收一次 -wal 体积
_WAL_CHECKPOINT_INTERVAL_SECONDS = 300

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


class DB(DBQueriesMixin):
    """异步 SQLite DB（aiosqlite）—— 连接池 + 批量写 + WAL checkpoint。

    业务查询/写入方法继承自 ``DBQueriesMixin``（见 ``api/db/queries.py``）。
    本类只管连接生命周期、批量写缓冲区、WAL checkpoint、schema 初始化委托。
    """

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

        # ── WAL 定期 checkpoint（P1-L）────────────────────
        self._checkpoint_running = False

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
        log.warning("DB 连接池 loop 漂移（%s → %s），重建连接池", self._pool_loop, loop)
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
        await conn.execute("PRAGMA cache_size=-64000")  # 64MB 页缓存
        await conn.execute("PRAGMA mmap_size=268435456")  # 256MB 内存映射 I/O
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

    # ── WAL 定期 checkpoint（P1-L）────────────────────

    async def start_checkpoint_timer(self) -> None:
        """后台协程：每 5 分钟执行一次 PRAGMA wal_checkpoint(TRUNCATE)；
        启动时首次执行一次 checkpoint。"""
        self._checkpoint_running = True
        try:
            # 启动时首次 checkpoint
            await self._run_checkpoint()
            while self._checkpoint_running:
                await asyncio.sleep(_WAL_CHECKPOINT_INTERVAL_SECONDS)
                await self._run_checkpoint()
        except asyncio.CancelledError:
            # 退出前再做一次 checkpoint
            await self._run_checkpoint()
            raise

    def stop_checkpoint_timer(self) -> None:
        self._checkpoint_running = False

    async def _run_checkpoint(self) -> None:
        """对每条写连接执行 wal_checkpoint(TRUNCATE)，抑制异常。"""
        for idx, conn in enumerate(self._connections):
            try:
                await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                log.warning("WAL checkpoint 写连接[%d] 失败（可忽略）", idx)

    # ── 读前自动 flush ──
    async def _ensure_flushed(self) -> None:
        """批量写入模式下，读操作前刷新缓冲区，确保数据可见性。"""
        await self._ensure_initialized()
        if self._batch_enabled:
            async with self._get_lock():
                await self._flush_buffer()

    # ── 结构 ──────────────────────────────────────
    async def _init_schema(self) -> None:
        """建表 + 索引 + 兼容补列迁移。

        v8.0 P0-3：DDL 实现下沉到 ``api/db/migrations.py`` 的 ``init_schema``，
        本方法只负责取写连接[0] + 其锁，委托执行。旧 ``DB`` 公开 API 零感知。
        """
        from .migrations import init_schema as _init_schema

        conn = self._connections[0]
        conn_lock = self._conn_locks[0]
        await _init_schema(conn, conn_lock)


__all__ = ["DB", "BatchWrite"]
