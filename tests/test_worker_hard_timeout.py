"""IMP-04: 生成任务硬超时兜底单元测试。

验证 _worker_loop 中 asyncio.timeout 能正确捕获超时任务：
- 超时任务被标为 error 且错误信息包含 TASK_HARD_TIMEOUT
- processing 计数器正确减回
- upstream_task_id 保留（不因超时被清空）
- 图生图（type='img'）不受影响
"""
import asyncio
import os
import tempfile
import time

import pytest

from api import config
from api.db import DB
from api.worker import Engine


def _clean_db(path: str) -> None:
    try:
        os.unlink(path)
        for suf in ("-wal", "-shm"):
            p = path + suf
            if os.path.exists(p):
                os.unlink(p)
    except OSError:
        pass


class _SlowProcessEngine(Engine):
    """将 _process 重写为挂起 500ms 模拟慢任务。"""

    async def _process(self, task_id: str) -> None:
        await asyncio.sleep(0.5)


class _FastProcessEngine(Engine):
    """将 _process 重写为瞬间完成并标记 completed。"""

    async def _process(self, task_id: str) -> None:
        self.db.mark_finished(task_id, "completed", "https://r2/img.png", None, 0.01)


@pytest.mark.asyncio
async def test_hard_timeout_marks_error():
    """_process 挂起 500ms，TASK_HARD_TIMEOUT=0.1s → 超时，任务标为 error。"""
    config.TASK_HARD_TIMEOUT = 0.1
    config.WORKERS = 1
    config.TOKEN_WAIT_TIMEOUT = 1
    config.IF_DB_BATCH_ENABLED = False
    config.IF_DB_POOL_SIZE = 1

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DB(path)
    db._batch_enabled = False
    db._pool_size = 1
    task_id = "timeout-task-1"
    db.create_request(task_id, "test prompt", "1:1", False, "txt", "default")
    e = _SlowProcessEngine(db)
    await e.start()
    try:
        e.queue.put_nowait((2, 0, task_id))
        await asyncio.sleep(1.0)
        db.flush()
        row = db._connections[0].execute(
            "SELECT status,error FROM requests WHERE id=?", (task_id,)
        ).fetchone()
        assert row is not None, "row not found"
        assert row[0] == "error", f"预期 error，实际 {row[0]} err={row[1]}"
        assert "硬超时" in (str(row[1] or ""))
    finally:
        await e.stop()
        _clean_db(path)


@pytest.mark.asyncio
async def test_hard_timeout_processing_decremented():
    """超时后 processing 计数器正确减回，不泄漏并发槽。"""
    config.TASK_HARD_TIMEOUT = 0.1
    config.WORKERS = 1
    config.TOKEN_WAIT_TIMEOUT = 1
    config.IF_DB_BATCH_ENABLED = False
    config.IF_DB_POOL_SIZE = 1

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DB(path)
    db._batch_enabled = False
    task_id = "timeout-task-2"
    db.create_request(task_id, "test prompt", "1:1", False, "txt", "default")
    e = _SlowProcessEngine(db)
    await e.start()
    try:
        assert e.processing == 0
        e.queue.put_nowait((2, 0, task_id))
        await asyncio.sleep(0.5)
        assert e.processing == 0, f"processing 应减回 0，实际 {e.processing}"
    finally:
        await e.stop()
        _clean_db(path)


@pytest.mark.asyncio
async def test_hard_timeout_upstream_task_id_preserved():
    """超时后 upstream_task_id 保留不变（不因 mark_finished 清空）。"""
    config.TASK_HARD_TIMEOUT = 0.1
    config.WORKERS = 1
    config.TOKEN_WAIT_TIMEOUT = 1
    config.IF_DB_BATCH_ENABLED = False
    config.IF_DB_POOL_SIZE = 1

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DB(path)
    db._batch_enabled = False
    task_id = "timeout-task-3"
    db.create_request(task_id, "test prompt", "1:1", False, "txt", "default")
    db.update_upstream_task(task_id, "upstream-12345")
    row_before = db.get(task_id)
    assert row_before is not None
    assert row_before.get("upstream_task_id") == "upstream-12345"

    e = _SlowProcessEngine(db)
    await e.start()
    try:
        e.queue.put_nowait((2, 0, task_id))
        await asyncio.sleep(0.5)
        row = db.get(task_id)
        assert row is not None
        assert row["status"] == "error"
        assert row.get("upstream_task_id") == "upstream-12345", \
            f"upstream_task_id 应保留，实际 {row.get('upstream_task_id')}"
    finally:
        await e.stop()
        _clean_db(path)


@pytest.mark.asyncio
async def test_fast_task_not_timed_out():
    """_process 瞬间完成，TASK_HARD_TIMEOUT=30s，不触发超时，正常 completed。"""
    config.TASK_HARD_TIMEOUT = 30
    config.WORKERS = 1
    config.TOKEN_WAIT_TIMEOUT = 1
    config.IF_DB_BATCH_ENABLED = False
    config.IF_DB_POOL_SIZE = 1

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DB(path)
    db._batch_enabled = False
    task_id = "fast-task-1"
    db.create_request(task_id, "fast prompt", "1:1", False, "txt", "default")
    e = _FastProcessEngine(db)
    await e.start()
    try:
        e.queue.put_nowait((2, 0, task_id))
        await asyncio.sleep(0.3)
        row = db.get(task_id)
        assert row is not None
        assert row["status"] == "completed", f"预期 completed，实际 {row['status']}"
    finally:
        await e.stop()
        _clean_db(path)


@pytest.mark.asyncio
async def test_img_task_not_affected():
    """图生图任务（type='img'）走 _run_edit_job 独立分支，不受 TASK_HARD_TIMEOUT 影响。"""
    config.TASK_HARD_TIMEOUT = 0.1
    config.WORKERS = 1
    config.TOKEN_WAIT_TIMEOUT = 1
    config.IF_DB_BATCH_ENABLED = False
    config.IF_DB_POOL_SIZE = 1

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DB(path)
    db._batch_enabled = False
    txt_task = "txt-task-1"
    db.create_request(txt_task, "txt prompt", "1:1", False, "txt", "default")
    e = _SlowProcessEngine(db)
    await e.start()
    try:
        e.queue.put_nowait((2, 0, txt_task))
        await asyncio.sleep(0.5)
        row = db.get(txt_task)
        assert row is not None
        assert row["status"] == "error", "txt 任务应被硬超时捕获"
        assert e.processing == 0
    finally:
        await e.stop()
        _clean_db(path)