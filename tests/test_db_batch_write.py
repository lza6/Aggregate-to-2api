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
import threading
import time

import pytest


def _make_db(enabled: bool = True, window: float = 0.2):
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
    finally:
        cfg.IF_DB_BATCH_ENABLED = old_enabled
        cfg.IF_DB_BATCH_WINDOW = old_window
    return db, path


def _cleanup(db, path: str):
    try:
        os.unlink(path)
        for suffix in ("-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.unlink(path + suffix)
    except OSError:
        pass


class TestBatchWriteEnabled:
    """批量写入开启时的行为验证。"""

    def test_batch_merges_multiple_writes_into_one_commit(self):
        """连续 3 次 create_request 后只 1 次 commit（通过 _commit_count 判定）。"""
        db, path = _make_db(enabled=True)
        try:
            before = db._commit_count

            db.create_request("t1", "prompt1", "1:1", False)
            db.create_request("t2", "prompt2", "4:3", True)
            db.create_request("t3", "prompt3", "16:9", False, "img", "anime")

            # 缓冲区有 3 条，尚未 commit
            assert len(db._write_buffer) == 3
            assert db._commit_count == before

            # flush 触发批量 commit
            db.flush()
            assert db._commit_count == before + 1
            assert len(db._write_buffer) == 0

            # 数据已落库
            assert db.get("t1")["status"] == "pending"
            assert db.get("t3")["type"] == "img"
        finally:
            _cleanup(db, path)

    def test_mark_started_and_finished_also_batched(self):
        """mark_started + mark_finished 也走缓冲，一次 flush 全部写入。"""
        db, path = _make_db(enabled=True)
        try:
            before = db._commit_count

            db.create_request("t1", "p", "1:1", False)
            db.mark_started("t1")
            db.mark_finished("t1", "completed", "https://img.url", None, 1.5)
            assert db._commit_count == before
            assert len(db._write_buffer) == 3

            db.flush()
            assert db._commit_count == before + 1
            row = db.get("t1")
            assert row["status"] == "completed"
            assert row["duration_sec"] == 1.5
        finally:
            _cleanup(db, path)

    def test_update_upstream_task_batched(self):
        """update_upstream_task 也走缓冲。"""
        db, path = _make_db(enabled=True)
        try:
            db.create_request("t1", "p", "1:1", False)
            db.flush()

            before = db._commit_count
            db.update_upstream_task("t1", "upstream-123")
            assert len(db._write_buffer) == 1

            db.flush()
            assert db._commit_count == before + 1
            assert db.get("t1")["upstream_task_id"] == "upstream-123"
        finally:
            _cleanup(db, path)

    def test_flush_after_stop_empties_buffer(self):
        """DB.flush() 在 stop 后缓冲区空。"""
        db, path = _make_db(enabled=True)
        try:
            db.create_request("t1", "p", "1:1", False)
            db.create_request("t2", "p", "16:9", True)
            assert len(db._write_buffer) == 2

            db.flush()
            assert len(db._write_buffer) == 0
            assert db.get("t1") is not None
            assert db.get("t2") is not None
        finally:
            _cleanup(db, path)

    def test_flush_is_idempotent(self):
        """多次 flush 安全，空 buffer 不崩溃。"""
        db, path = _make_db(enabled=True)
        try:
            before = db._commit_count
            db.flush()
            db.flush()
            db.flush()
            assert db._commit_count == before  # 空 buffer 不 commit
        finally:
            _cleanup(db, path)

    def test_concurrent_append_and_flush(self):
        """多线程并发 enqueue + flush 不崩溃（竞态模拟）。"""
        db, path = _make_db(enabled=True)
        try:
            errors = []

            def writer(n: int):
                try:
                    for i in range(n):
                        db.create_request(f"c{i}-{threading.get_ident()}", "p", "1:1", False)
                except Exception as e:
                    errors.append(e)

            def flusher(count: int):
                try:
                    for _ in range(count):
                        db.flush()
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(e)

            threads = []
            for _ in range(3):
                threads.append(threading.Thread(target=writer, args=(20,)))
            threads.append(threading.Thread(target=flusher, args=(10,)))

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert not errors, f"并发异常: {errors}"
            db.flush()
        finally:
            _cleanup(db, path)


class TestBatchWriteDisabled:
    """IF_DB_BATCH_ENABLED=0 时保持原行为。"""

    def test_each_write_commits_immediately(self):
        """每操作 1 次 commit（通过 _commit_count 判定）。"""
        db, path = _make_db(enabled=False)
        try:
            before = db._commit_count

            db.create_request("t1", "p", "1:1", False)
            assert db._commit_count == before + 1
            db.mark_started("t1")
            assert db._commit_count == before + 2
            db.mark_finished("t1", "completed", "https://img.url", None, 1.0)
            assert db._commit_count == before + 3

            # buffer 为空
            assert len(db._write_buffer) == 0
        finally:
            _cleanup(db, path)

    def test_batch_controls_off_no_buffer_usage(self):
        """禁用时 _write_buffer 始终为空。"""
        db, path = _make_db(enabled=False)
        try:
            db.create_request("t1", "p", "1:1", False)
            assert len(db._write_buffer) == 0
            db.mark_started("t1")
            assert len(db._write_buffer) == 0
            db.mark_finished("t1", "completed", "https://img.url", None, 1.0)
            assert len(db._write_buffer) == 0
        finally:
            _cleanup(db, path)

    def test_flush_noop_when_disabled(self):
        """禁用时 flush 无害。"""
        db, path = _make_db(enabled=False)
        try:
            db.create_request("t1", "p", "1:1", False)
            db.flush()  # 不应报错
            assert db.get("t1") is not None
        finally:
            _cleanup(db, path)


class TestBatchTimer:
    """后台定时器协程验证。"""

    @pytest.mark.asyncio
    async def test_timer_flushes_after_window(self):
        """定时器在 batch_window 秒后自动 flush。"""
        db, path = _make_db(enabled=True, window=0.05)
        try:
            before = db._commit_count

            timer = asyncio.create_task(db.start_batch_timer())
            db.create_request("t1", "p", "1:1", False)
            db.create_request("t2", "p", "16:9", True)

            # 等 2 个窗口期，确保 timer 触发 flush
            await asyncio.sleep(0.15)
            assert db._commit_count >= before + 1
            assert len(db._write_buffer) == 0

            # 数据已落库
            assert db.get("t1") is not None
            assert db.get("t2") is not None

            timer.cancel()
            try:
                await timer
            except asyncio.CancelledError:
                pass
        finally:
            _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_cancelled_timer_flushes_remaining(self):
        """Cancel 时 flush 残留数据。"""
        db, path = _make_db(enabled=True, window=10.0)
        try:
            timer = asyncio.create_task(db.start_batch_timer())
            # 给任务一点时间启动
            await asyncio.sleep(0.02)
            db.create_request("t1", "p", "1:1", False)
            db.create_request("t2", "p", "16:9", True)

            timer.cancel()
            try:
                await timer
            except asyncio.CancelledError:
                pass

            # Cancel 时 flush 残留数据
            row1 = db.get("t1")
            row2 = db.get("t2")
            assert row1 is not None, f"t1 未找到 (buffer={len(db._write_buffer)})"
            assert row2 is not None, f"t2 未找到"
        finally:
            _cleanup(db, path)


class TestIdempotentRecovery:
    """幂等重放：已 flush 的数据可查询，重复 flush 不丢/不崩。"""

    def test_flushed_data_is_queryable(self):
        """flush 后数据立即可查询。"""
        db, path = _make_db(enabled=True)
        try:
            db.create_request("t1", "p", "1:1", False)
            db.flush()
            row = db.get("t1")
            assert row is not None
            assert row["status"] == "pending"

            db.mark_finished("t1", "completed", "https://img.url", None, 2.0)
            db.flush()
            row = db.get("t1")
            assert row["status"] == "completed"
        finally:
            _cleanup(db, path)

    def test_repeated_flush_does_not_duplicate(self):
        """重复 flush 不产生重复数据（幂等）。"""
        db, path = _make_db(enabled=True)
        try:
            db.create_request("t1", "p", "1:1", False)
            db.flush()
            db.flush()
            db.flush()
            rows = db._conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
            assert rows == 1
        finally:
            _cleanup(db, path)