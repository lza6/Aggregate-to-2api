"""IMP-25: SQLite 批量写入测试。

覆盖场景：
- 批量窗口合并：连续 3 次 create_request 后只 1 次 commit
- IF_DB_BATCH_ENABLED=0 时保持原行为（每操作 1 次 commit）
- DB.flush() 在 stop 后缓冲区空
- 幂等重放：flush 后数据可查询
"""

import asyncio
import os
import tempfile

import pytest


async def _make_db(enabled: bool = True, window: float = 0.2):
    """创建临时 DB 实例，返回 (db, path)。"""
    import api.config as cfg
    from api.db import DB

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    old_enabled = cfg.IF_DB_BATCH_ENABLED
    old_window = cfg.IF_DB_BATCH_WINDOW
    cfg.IF_DB_BATCH_ENABLED = enabled
    cfg.IF_DB_BATCH_WINDOW = window
    try:
        db = DB(path)
        await db._ensure_initialized()
    finally:
        cfg.IF_DB_BATCH_ENABLED = old_enabled
        cfg.IF_DB_BATCH_WINDOW = old_window
    return db, path


async def _cleanup(db, path: str):
    try:
        await db.close()
    except Exception:
        pass
    try:
        os.unlink(path)
        for suffix in ("-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.unlink(path + suffix)
    except OSError:
        pass


class TestBatchWriteEnabled:
    """批量写入开启时的行为验证。"""

    @pytest.mark.asyncio
    async def test_batch_merges_multiple_writes_into_one_commit(self):
        """连续 3 次 create_request 后只 1 次 commit（通过 _commit_count 判定）。"""
        db, path = await _make_db(enabled=True)
        try:
            before = db._commit_count

            await db.create_request("t1", "prompt1", "1:1", False)
            await db.create_request("t2", "prompt2", "4:3", True)
            await db.create_request("t3", "prompt3", "16:9", False, "img", "anime")

            # 缓冲区有 3 条，尚未 commit
            assert len(db._write_buffer) == 3
            assert db._commit_count == before

            # flush 触发批量 commit
            await db.flush()
            assert db._commit_count == before + 1
            assert len(db._write_buffer) == 0

            # 数据已落库
            row1 = await db.get("t1")
            assert row1["status"] == "pending"
            row3 = await db.get("t3")
            assert row3["type"] == "img"
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_mark_started_and_finished_also_batched(self):
        """mark_started + mark_finished 也走缓冲，一次 flush 全部写入。"""
        db, path = await _make_db(enabled=True)
        try:
            before = db._commit_count

            await db.create_request("t1", "p", "1:1", False)
            await db.mark_started("t1")
            await db.mark_finished("t1", "completed", "https://img.url", None, 1.5)
            assert db._commit_count == before
            assert len(db._write_buffer) == 3

            await db.flush()
            assert db._commit_count == before + 1
            row = await db.get("t1")
            assert row["status"] == "completed"
            assert row["duration_sec"] == 1.5
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_update_upstream_task_batched(self):
        """update_upstream_task 也走缓冲。"""
        db, path = await _make_db(enabled=True)
        try:
            await db.create_request("t1", "p", "1:1", False)
            await db.flush()

            before = db._commit_count
            await db.update_upstream_task("t1", "upstream-123")
            assert len(db._write_buffer) == 1

            await db.flush()
            assert db._commit_count == before + 1
            row = await db.get("t1")
            assert row["upstream_task_id"] == "upstream-123"
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_flush_after_stop_empties_buffer(self):
        """DB.flush() 在 stop 后缓冲区空。"""
        db, path = await _make_db(enabled=True)
        try:
            await db.create_request("t1", "p", "1:1", False)
            await db.create_request("t2", "p", "16:9", True)
            assert len(db._write_buffer) == 2

            await db.flush()
            assert len(db._write_buffer) == 0
            assert await db.get("t1") is not None
            assert await db.get("t2") is not None
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_flush_is_idempotent(self):
        """多次 flush 安全，空 buffer 不崩溃。"""
        db, path = await _make_db(enabled=True)
        try:
            before = db._commit_count
            await db.flush()
            await db.flush()
            await db.flush()
            assert db._commit_count == before  # 空 buffer 不 commit
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_reads_wait_for_inflight_flush_lock_even_when_buffer_empty(self):
        """读不能绕过 flush 锁：buffer 已 swap 为空但 commit 尚未完成时也必须等待。"""
        db, path = await _make_db(enabled=True)
        lock = None
        try:
            await db.create_request("t-lock-read", "p", "1:1", False)
            await db.flush()
            lock = db._get_lock()
            await lock.acquire()
            reader = asyncio.create_task(db.get("t-lock-read"))
            await asyncio.sleep(0)
            assert not reader.done(), "读操作绕过了正在进行的 flush 临界区"
            lock.release()
            row = await reader
            assert row is not None
            assert row["status"] == "pending"
        finally:
            if lock is not None and lock.locked():
                lock.release()
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_concurrent_append_and_flush(self):
        """多协程并发 enqueue + flush 不崩溃（竞态模拟）。"""
        db, path = await _make_db(enabled=True)
        try:
            errors = []

            async def writer(n: int, wid: int):
                try:
                    for i in range(n):
                        await db.create_request(f"c{i}-{wid}", "p", "1:1", False)
                except Exception as e:
                    errors.append(e)

            async def flusher(count: int):
                try:
                    for _ in range(count):
                        await db.flush()
                        await asyncio.sleep(0.001)
                except Exception as e:
                    errors.append(e)

            tasks = []
            for i in range(3):
                tasks.append(asyncio.create_task(writer(20, i)))
            tasks.append(asyncio.create_task(flusher(10)))

            await asyncio.gather(*tasks)

            assert not errors, f"并发异常: {errors}"
            await db.flush()
        finally:
            await _cleanup(db, path)


class TestBatchWriteDisabled:
    """IF_DB_BATCH_ENABLED=0 时保持原行为。"""

    @pytest.mark.asyncio
    async def test_each_write_commits_immediately(self):
        """每操作 1 次 commit（通过 _commit_count 判定）。"""
        db, path = await _make_db(enabled=False)
        try:
            before = db._commit_count

            await db.create_request("t1", "p", "1:1", False)
            assert db._commit_count == before + 1
            await db.mark_started("t1")
            assert db._commit_count == before + 2
            await db.mark_finished("t1", "completed", "https://img.url", None, 1.0)
            assert db._commit_count == before + 3

            # buffer 为空
            assert len(db._write_buffer) == 0
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_batch_controls_off_no_buffer_usage(self):
        """禁用时 _write_buffer 始终为空。"""
        db, path = await _make_db(enabled=False)
        try:
            await db.create_request("t1", "p", "1:1", False)
            assert len(db._write_buffer) == 0
            await db.mark_started("t1")
            assert len(db._write_buffer) == 0
            await db.mark_finished("t1", "completed", "https://img.url", None, 1.0)
            assert len(db._write_buffer) == 0
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_flush_noop_when_disabled(self):
        """禁用时 flush 无害。"""
        db, path = await _make_db(enabled=False)
        try:
            await db.create_request("t1", "p", "1:1", False)
            await db.flush()  # 不应报错
            assert await db.get("t1") is not None
        finally:
            await _cleanup(db, path)


class TestBatchTimer:
    """后台定时器协程验证。"""

    @pytest.mark.asyncio
    async def test_timer_flushes_after_window(self):
        """定时器在 batch_window 秒后自动 flush。"""
        db, path = await _make_db(enabled=True, window=0.05)
        try:
            before = db._commit_count

            timer = asyncio.create_task(db.start_batch_timer())
            await db.create_request("t1", "p", "1:1", False)
            await db.create_request("t2", "p", "16:9", True)

            # 等 2 个窗口期，确保 timer 触发 flush
            await asyncio.sleep(0.15)
            assert db._commit_count >= before + 1
            assert len(db._write_buffer) == 0

            # 数据已落库
            assert await db.get("t1") is not None
            assert await db.get("t2") is not None

            timer.cancel()
            try:
                await timer
            except asyncio.CancelledError:
                pass
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_cancelled_timer_flushes_remaining(self):
        """Cancel 时 flush 残留数据。"""
        db, path = await _make_db(enabled=True, window=10.0)
        try:
            timer = asyncio.create_task(db.start_batch_timer())
            # 给任务一点时间启动
            await asyncio.sleep(0.02)
            await db.create_request("t1", "p", "1:1", False)
            await db.create_request("t2", "p", "16:9", True)

            timer.cancel()
            try:
                await timer
            except asyncio.CancelledError:
                pass

            # Cancel 时 flush 残留数据
            row1 = await db.get("t1")
            row2 = await db.get("t2")
            assert row1 is not None, f"t1 未找到 (buffer={len(db._write_buffer)})"
            assert row2 is not None, "t2 未找到"
        finally:
            await _cleanup(db, path)


class TestIdempotentRecovery:
    """幂等重放：已 flush 的数据可查询，重复 flush 不丢/不崩。"""

    @pytest.mark.asyncio
    async def test_flushed_data_is_queryable(self):
        """flush 后数据立即可查询。"""
        db, path = await _make_db(enabled=True)
        try:
            await db.create_request("t1", "p", "1:1", False)
            await db.flush()
            row = await db.get("t1")
            assert row is not None
            assert row["status"] == "pending"

            await db.mark_finished("t1", "completed", "https://img.url", None, 2.0)
            await db.flush()
            row = await db.get("t1")
            assert row["status"] == "completed"
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_repeated_flush_does_not_duplicate(self):
        """重复 flush 不产生重复数据（幂等）。"""
        db, path = await _make_db(enabled=True)
        try:
            await db.create_request("t1", "p", "1:1", False)
            await db.flush()
            await db.flush()
            await db.flush()
            cursor = await db._connections[0].execute("SELECT COUNT(*) FROM requests")
            row = await cursor.fetchone()
            assert row[0] == 1
        finally:
            await _cleanup(db, path)
