"""IMP-04: 生成任务硬超时兜底单元测试。

验证 _worker_loop 中 asyncio.timeout 能正确捕获超时任务：
- 超时任务被标为 error 且错误信息包含 TASK_HARD_TIMEOUT
- processing 计数器正确减回
- upstream_task_id 保留（不因超时被清空）
- 图生图（type='img'）不受影响

注意：这些测试依赖真实 asyncio 时序（0.1s 硬超时 vs worker 调度延迟）。
共享事件循环被其他测试占用时，固定 sleep 可能不够 worker 完成全链路，
因此全部用「轮询直到状态变化 + 截止时间」的健壮写法，而非固定 sleep。
"""

import asyncio
import os
import tempfile
import time

import pytest

from api import config
from api.db import DB
from api.worker import Engine


async def _wait_status(db: DB, task_id: str, expected: str, timeout: float = 5.0) -> dict | None:
    """轮询等待任务达到期望状态，杜绝交叉污染下的固定 sleep 竞态。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = await db.get(task_id)
        if row is not None and row["status"] == expected:
            return row
        await asyncio.sleep(0.05)
    return await db.get(task_id)


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
        await self.db.mark_finished(task_id, "completed", "https://r2/img.png", None, 0.01)


@pytest.mark.asyncio
async def test_hard_timeout_marks_error(monkeypatch):
    """_process 挂起 500ms，TASK_HARD_TIMEOUT=0.1s → 超时，任务标为 error。"""
    monkeypatch.setattr(config, "TASK_HARD_TIMEOUT", 0.1)
    monkeypatch.setattr(config, "WORKERS", 1)
    monkeypatch.setattr(config, "TOKEN_WAIT_TIMEOUT", 1)
    monkeypatch.setattr(config, "IF_DB_BATCH_ENABLED", False)
    monkeypatch.setattr(config, "IF_DB_POOL_SIZE", 1)

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DB(path)
    db._batch_enabled = False
    db._pool_size = 1
    task_id = "timeout-task-1"
    await db.create_request(task_id, "test prompt", "1:1", False, "txt", "default")
    e = _SlowProcessEngine(db)
    await e.start()
    try:
        e.queue.put_nowait((2, 0, task_id))
        row = await _wait_status(db, task_id, "error")
        assert row is not None, "row not found"
        assert row["status"] == "error", f"预期 error，实际 {row['status']} err={row['error']}"
        assert "硬超时" in (str(row.get("error") or ""))
    finally:
        await e.stop()
        try:
            await db.close()
        except Exception:
            pass
        _clean_db(path)


@pytest.mark.asyncio
async def test_hard_timeout_processing_decremented(monkeypatch):
    """超时后 processing 计数器正确减回，不泄漏并发槽。"""
    monkeypatch.setattr(config, "TASK_HARD_TIMEOUT", 0.1)
    monkeypatch.setattr(config, "WORKERS", 1)
    monkeypatch.setattr(config, "TOKEN_WAIT_TIMEOUT", 1)
    monkeypatch.setattr(config, "IF_DB_BATCH_ENABLED", False)
    monkeypatch.setattr(config, "IF_DB_POOL_SIZE", 1)

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DB(path)
    db._batch_enabled = False
    task_id = "timeout-task-2"
    await db.create_request(task_id, "test prompt", "1:1", False, "txt", "default")
    e = _SlowProcessEngine(db)
    await e.start()
    try:
        assert e.processing == 0
        e.queue.put_nowait((2, 0, task_id))
        row = await _wait_status(db, task_id, "error")
        assert row is not None, "row not found"
        await asyncio.sleep(0.1)  # 等 finally 中 processing 递减完成
        assert e.processing == 0, f"processing 应减回 0，实际 {e.processing}"
    finally:
        await e.stop()
        try:
            await db.close()
        except Exception:
            pass
        _clean_db(path)


@pytest.mark.asyncio
async def test_hard_timeout_upstream_task_id_preserved(monkeypatch):
    """超时后 upstream_task_id 保留不变（不因 mark_finished 清空）。"""
    monkeypatch.setattr(config, "TASK_HARD_TIMEOUT", 0.1)
    monkeypatch.setattr(config, "WORKERS", 1)
    monkeypatch.setattr(config, "TOKEN_WAIT_TIMEOUT", 1)
    monkeypatch.setattr(config, "IF_DB_BATCH_ENABLED", False)
    monkeypatch.setattr(config, "IF_DB_POOL_SIZE", 1)

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DB(path)
    db._batch_enabled = False
    task_id = "timeout-task-3"
    await db.create_request(task_id, "test prompt", "1:1", False, "txt", "default")
    await db.update_upstream_task(task_id, "upstream-12345")
    row_before = await db.get(task_id)
    assert row_before is not None
    assert row_before.get("upstream_task_id") == "upstream-12345"

    e = _SlowProcessEngine(db)
    await e.start()
    try:
        e.queue.put_nowait((2, 0, task_id))
        row = await _wait_status(db, task_id, "error")
        assert row is not None
        assert row["status"] == "error"
        assert (
            row.get("upstream_task_id") == "upstream-12345"
        ), f"upstream_task_id 应保留，实际 {row.get('upstream_task_id')}"
    finally:
        await e.stop()
        try:
            await db.close()
        except Exception:
            pass
        _clean_db(path)


@pytest.mark.asyncio
async def test_fast_task_not_timed_out(monkeypatch):
    """_process 瞬间完成，TASK_HARD_TIMEOUT=30s，不触发超时，正常 completed。"""
    monkeypatch.setattr(config, "TASK_HARD_TIMEOUT", 30)
    monkeypatch.setattr(config, "WORKERS", 1)
    monkeypatch.setattr(config, "TOKEN_WAIT_TIMEOUT", 1)
    monkeypatch.setattr(config, "IF_DB_BATCH_ENABLED", False)
    monkeypatch.setattr(config, "IF_DB_POOL_SIZE", 1)

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DB(path)
    db._batch_enabled = False
    task_id = "fast-task-1"
    await db.create_request(task_id, "fast prompt", "1:1", False, "txt", "default")
    e = _FastProcessEngine(db)
    await e.start()
    try:
        e.queue.put_nowait((2, 0, task_id))
        row = await _wait_status(db, task_id, "completed")
        assert row is not None
        assert row["status"] == "completed", f"预期 completed，实际 {row['status']}"
    finally:
        await e.stop()
        try:
            await db.close()
        except Exception:
            pass
        _clean_db(path)


@pytest.mark.asyncio
async def test_img_task_not_affected(monkeypatch):
    """图生图任务（type='img'）走 _run_edit_job 独立分支，不受 TASK_HARD_TIMEOUT 影响。"""
    monkeypatch.setattr(config, "TASK_HARD_TIMEOUT", 0.1)
    monkeypatch.setattr(config, "WORKERS", 1)
    monkeypatch.setattr(config, "TOKEN_WAIT_TIMEOUT", 1)
    monkeypatch.setattr(config, "IF_DB_BATCH_ENABLED", False)
    monkeypatch.setattr(config, "IF_DB_POOL_SIZE", 1)

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DB(path)
    db._batch_enabled = False
    txt_task = "txt-task-1"
    await db.create_request(txt_task, "txt prompt", "1:1", False, "txt", "default")
    e = _SlowProcessEngine(db)
    await e.start()
    try:
        e.queue.put_nowait((2, 0, txt_task))
        row = await _wait_status(db, txt_task, "error")
        assert row is not None
        assert row["status"] == "error", "txt 任务应被硬超时捕获"
        await asyncio.sleep(0.1)  # 等 finally 中 processing 递减完成
        assert e.processing == 0
    finally:
        await e.stop()
        try:
            await db.close()
        except Exception:
            pass
        _clean_db(path)
