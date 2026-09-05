"""P1-3: worker 批量循环（_worker_batch_loop）任务级异常回收的终态唯一化回归测试。

背景：v6.8.1 release notes 声称已修「done/pending 分支重复标记竞态」。本套件验证
《下一步改进指南》P1-3 闭环所需的三个分支：
  a) cancel 前已完成 —— pending 分支对 DB 已落终态的任务不覆盖，终态唯一。
  b) 任务抛异常 —— done 分支异常兜底落 error，且唯一。
  c) 超时标记覆盖真实结果 —— 真实完成结果（completed + image_url）不被超时/异常路径覆盖。

核心测量：把 _process 改写为受控假实现（模拟先落库/后落库/抛异常/超时），用 _CountingDB
包装真实 DB 计数 mark_finished 调用次数，跑完一组 batch 后断言 DB 终态唯一。

注意：引擎用 _process 受控返回码契约 = 返回 "completed"/"error" 表示已在 DB 落库；
本套件通过子类覆写 _process 直接走 done/pending 两分支，验证 batch loop 不再二次覆盖。
"""

import asyncio
import time

import pytest

from api import config
from api.worker import Engine


class _CountingDB:
    """薄包装真实 DB：只计数 mark_finished 调用（终态唯一性证据），其余委托。"""

    def __init__(self, db):
        self._db = db
        self.mark_finished_calls: list[tuple[str, str]] = []  # (tid, status)

    async def get(self, task_id):
        return await self._db.get(task_id)

    async def mark_started(self, task_id):
        return await self._db.mark_started(task_id)

    async def mark_finished(self, task_id, status, image_url, error, duration, image_base64=None, image_mime=None):
        self.mark_finished_calls.append((task_id, status))
        return await self._db.mark_finished(
            task_id, status, image_url, error, duration, image_base64, image_mime
        )

    async def recover_stale_tasks(self, **kw) -> int:
        return 0


async def _wait_status(db, task_id: str, expected: str, timeout: float = 5.0) -> dict | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = await db.get(task_id)
        if row is not None and row["status"] == expected:
            return row
        await asyncio.sleep(0.05)
    return await db.get(task_id)


def _set_batch_config(monkeypatch, hard_timeout: float = 0.1, batch_size: int = 16) -> None:
    """切换到批量 worker 分支 + 隔离 DB 池，避免默认配置干扰。"""
    monkeypatch.setattr(config, "IF_WORKER_BATCH_ENABLED", True)
    monkeypatch.setattr(config, "IF_WORKER_BATCH_SIZE", batch_size)
    monkeypatch.setattr(config, "IF_WORKER_AUTO", False)
    monkeypatch.setattr(config, "WORKERS", 1)
    monkeypatch.setattr(config, "TASK_HARD_TIMEOUT", hard_timeout)
    monkeypatch.setattr(config, "IF_PERSISTENT_QUEUE_ENABLED", False)
    # 关闭 DB 批量写入，保证读能立即看到写入（避免 flush 时序噪声）
    monkeypatch.setattr(config, "IF_DB_BATCH_ENABLED", False)
    monkeypatch.setattr(config, "IF_DB_POOL_SIZE", 1)


async def _drive_batch(e: Engine, db, task_id: str, expected_status: str) -> dict | None:
    """把单个任务放进队列，跑一个 batch-loop 协程，等待终态后干净收尾。"""
    stop_event = asyncio.Event()
    wtask = asyncio.create_task(e._worker_batch_loop(0, stop_event))
    try:
        # 让 pos 计数从 0 开始，worker 内部 task_done 匹配
        e.queue.put_nowait((2, 0, task_id))
        row = await _wait_status(db, task_id, expected_status, timeout=5.0)
    finally:
        stop_event.set()
        try:
            await asyncio.wait_for(wtask, timeout=2.0)
        except TimeoutError:
            wtask.cancel()
            try:
                await wtask
            except asyncio.CancelledError:
                pass
            except BaseException:
                pass
        except asyncio.CancelledError:
            pass
    if row is None:
        row = await db.get(task_id)
    return row


class _RaiseProcessEngine(Engine):
    """_process 立即抛异常（未落终态）→ 应走 done 分支异常兜底落 error。"""

    async def _process(self, task_id):
        await self.db.mark_started(task_id)
        raise RuntimeError("boom-branch-b")


class _CompletedThenRaiseEngine(Engine):
    """_process 先落 completed 再抛异常（模拟 _finish 后 DLQ 推送失败）→ 不覆盖真实结果。"""

    async def _process(self, task_id):
        await self.db.mark_started(task_id)
        await self.db.mark_finished(task_id, "completed", "https://r2/kept.png", None, 0.01)
        raise RuntimeError("boom-after-complete")


class _CompletedThenSlowEngine(Engine):
    """_process 先落 completed 再挂起超时（cancel 前已完成）→ pending 分支不覆盖终态。"""

    async def _process(self, task_id):
        await self.db.mark_started(task_id)
        await self.db.mark_finished(task_id, "completed", "https://r2/early.png", None, 0.01)
        await asyncio.sleep(1.0)  # 超过 hard_timeout，保证落到 pending


@pytest.mark.asyncio
async def test_branch_a_cancel_before_completed_terminal_unique(tmp_db, monkeypatch):
    """cancel 前已完成：pending 分支看到 DB 已 completed，不得再覆盖，终态唯一。"""
    _set_batch_config(monkeypatch, hard_timeout=0.1)
    db = _CountingDB(tmp_db)
    tmp_db._batch_enabled = False
    e = _CompletedThenSlowEngine(db)
    e._started = False
    e._workers = []
    task_id = "batch-cancel-before-completed"
    await tmp_db.create_request(task_id, "p", "1:1", False, "txt", "default")

    row = await _drive_batch(e, db, task_id, "completed")

    assert row is not None
    assert row["status"] == "completed", f"completed 应保留，实际 {row['status']} err={row.get('error')}"
    assert row.get("image_url") == "https://r2/early.png"
    # 终态唯一：mark_finished(completed) 只落一次，超时路径不得补写
    completed_calls = [s for t, s in db.mark_finished_calls if t == task_id]
    assert completed_calls == ["completed"], f"mark_finished 应只落一次 completed，实际 {completed_calls}"
    assert row.get("error") is None


@pytest.mark.asyncio
async def test_branch_b_task_raises_marks_error_unique(tmp_db, monkeypatch):
    """任务抛异常：done 分支异常兜底落 error，且唯一（不重复 mark_finished）。"""
    _set_batch_config(monkeypatch, hard_timeout=0.1)
    db = _CountingDB(tmp_db)
    tmp_db._batch_enabled = False
    e = _RaiseProcessEngine(db)
    e._started = False
    e._workers = []
    task_id = "batch-task-raises"
    await tmp_db.create_request(task_id, "p", "1:1", False, "txt", "default")

    row = await _drive_batch(e, db, task_id, "error")

    assert row is not None
    assert row["status"] == "error", f"预期 error，实际 {row['status']}"
    assert "boom-branch-b" in str(row.get("error") or "")
    error_calls = [s for t, s in db.mark_finished_calls if t == task_id]
    assert error_calls == ["error"], f"mark_finished 应只落一次 error，实际 {error_calls}"


@pytest.mark.asyncio
async def test_branch_c_timeout_does_not_overwrite_real_result(tmp_db, monkeypatch):
    """超时标记不覆盖真实结果：真实 completed（含 image_url）不被完成后的二次写入覆盖。"""
    _set_batch_config(monkeypatch, hard_timeout=0.1)
    db = _CountingDB(tmp_db)
    tmp_db._batch_enabled = False
    e = _CompletedThenRaiseEngine(db)
    e._started = False
    e._workers = []
    task_id = "batch-timeout-no-overwrite"
    await tmp_db.create_request(task_id, "p", "1:1", False, "txt", "default")

    row = await _drive_batch(e, db, task_id, "completed")

    assert row is not None
    assert row["status"] == "completed", f"真实 completed 不应被覆盖，实际 {row['status']} err={row.get('error')}"
    assert row.get("image_url") == "https://r2/kept.png", "真实出图 URL 不得被异常兜底覆盖"
    calls = [s for t, s in db.mark_finished_calls if t == task_id]
    assert calls == ["completed"], f"终态应唯一且为 completed，实际 {calls}"


@pytest.mark.asyncio
async def test_single_worker_hard_timeout_does_not_overwrite_completed(tmp_db, monkeypatch):
    """C1 修复：单 worker 路径 _worker_loop 的硬超时兜底不得覆盖已落库 completed。

    构造 _process 先落 completed（含 image_url）再挂起 → asyncio.timeout 到期触发
    except asyncio.TimeoutError。修复前该分支无条件 mark_finished("error") 覆盖 + 抹 image_url；
    修复后先 db.get 查终态，已是 completed 则不覆盖（image_url 保留）。
    """

    monkeypatch.setattr(config, "TASK_HARD_TIMEOUT", 0.05)
    monkeypatch.setattr(config, "WORKERS", 1)
    monkeypatch.setattr(config, "TOKEN_WAIT_TIMEOUT", 1)
    monkeypatch.setattr(config, "IF_DB_BATCH_ENABLED", False)
    monkeypatch.setattr(config, "IF_DB_POOL_SIZE", 1)

    db = _CountingDB(tmp_db)
    tmp_db._batch_enabled = False
    tmp_db._pool_size = 1

    class _CompletedThenSlowEngine(Engine):
        async def start(self) -> None:
            self._started = True
            self._workers = [self._create_worker(i) for i in range(config.WORKERS)]

        async def _process(self, task_id: str) -> None:
            # 先落库 completed（真实结果），再挂起触发 hard timeout
            await self.db.mark_finished(task_id, "completed", "https://r2/c1.png", None, 0.01)
            await asyncio.sleep(1.0)  # > TASK_HARD_TIMEOUT

    e = _CompletedThenSlowEngine(db)
    await e.start()
    try:
        task_id = "c1-timeout-no-overwrite"
        await tmp_db.create_request(task_id, "p", "1:1", False, "txt", "default")
        e.queue.put_nowait((2, 0, task_id))
        # 轮询直到终态；硬超时后应保持 completed（未覆盖）
        row = None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            row = await db.get(task_id)
            if row is not None and row["status"] in ("completed", "error"):
                break
            await asyncio.sleep(0.05)
        assert row is not None
        assert row["status"] == "completed", f"硬超时不得覆盖已落库 completed，实际 {row['status']} err={row.get('error')}"
        assert row.get("image_url") == "https://r2/c1.png", "已提交 image_url 不得被硬超时抹成 None"
        # 终态唯一：同一 task 只落一次，且为 completed
        calls = [s for t, s in db.mark_finished_calls if t == task_id]
        assert calls == ["completed"], f"单 worker 硬超时终态应唯一且为 completed，实际 {calls}"
    finally:
        await e.stop()
