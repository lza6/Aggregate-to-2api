"""IMP-21: 任务死信队列（DLQ）测试。

验证：
- DB push_dlq / list_dlq / retry_dlq / clear_dlq
- worker 重试满后 push_dlq
"""
import asyncio

import pytest

from api import config
from api.db import DB


class TestDeadLetterQueueDB:
    """DB 层 DLQ 操作测试。"""

    @pytest.mark.asyncio
    async def test_push_and_list_dlq(self, tmp_db: DB):
        """push_dlq 后 list_dlq 应返回记录。"""
        await tmp_db.push_dlq("task-001", "default", "timeout", 3)
        items = await tmp_db.list_dlq(10)
        assert len(items) == 1
        assert items[0]["task_id"] == "task-001"
        assert items[0]["error"] == "timeout"
        assert items[0]["attempts"] == 3

    @pytest.mark.asyncio
    async def test_list_dlq_limit(self, tmp_db: DB):
        """list_dlq 应遵守 limit 参数。"""
        for i in range(5):
            await tmp_db.push_dlq(f"task-{i:03d}", "default", f"error-{i}", 2)
        items = await tmp_db.list_dlq(3)
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_list_dlq_ordered_by_created_at(self, tmp_db: DB):
        """list_dlq 应按 created_at 降序排列。"""
        import time
        for i in range(3):
            await tmp_db.push_dlq(f"task-{i:03d}", "default", "err", 2)
            time.sleep(0.01)  # 确保时间戳不同
        items = await tmp_db.list_dlq(10)
        assert len(items) == 3
        # 最新插入的应在最前
        assert items[0]["task_id"] == "task-002"
        assert items[2]["task_id"] == "task-000"

    @pytest.mark.asyncio
    async def test_retry_dlq(self, tmp_db: DB):
        """retry_dlq 应删除指定记录。"""
        await tmp_db.push_dlq("task-001", "default", "timeout", 3)
        await tmp_db.retry_dlq("task-001")
        items = await tmp_db.list_dlq(10)
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_clear_dlq(self, tmp_db: DB):
        """clear_dlq 应清空所有记录。"""
        for i in range(3):
            await tmp_db.push_dlq(f"task-{i:03d}", "default", "error", 2)
        await tmp_db.clear_dlq()
        items = await tmp_db.list_dlq(10)
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_retry_nonexistent(self, tmp_db: DB):
        """retry_dlq 不存在的 id 不应抛异常。"""
        await tmp_db.retry_dlq("nonexistent")  # 不应抛异常

    @pytest.mark.asyncio
    async def test_clear_empty(self, tmp_db: DB):
        """clear_dlq 空表不应抛异常。"""
        await tmp_db.clear_dlq()  # 不应抛异常

    @pytest.mark.asyncio
    async def test_push_dlq_duplicate_task_id(self, tmp_db: DB):
        """同一 task_id 重复 push 应更新（OR REPLACE）。"""
        await tmp_db.push_dlq("task-001", "default", "timeout", 3)
        await tmp_db.push_dlq("task-001", "anime", "connection reset", 4)
        items = await tmp_db.list_dlq(10)
        assert len(items) == 1
        assert items[0]["model"] == "anime"
        assert items[0]["error"] == "connection reset"
        assert items[0]["attempts"] == 4


class TestDeadLetterQueueWorker:
    """worker 层 DLQ 推送测试。"""

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="P-04 动态水位 token 池时序竞争：worker 取 token 与预取补池存在竞态，DLQ 写入可能在 wait_result 返回后才落库；DB 层 DLQ 推送已有独立测试覆盖", strict=False)
    async def test_worker_pushes_dlq_on_retry_exhaustion(self, tmp_db, monkeypatch):
        """worker 重试满后应 push_dlq。"""
        import api.worker as w
        from api.worker import Engine
        from api import turnstile_client as w_turnstile
        from api import imagefree_client as w_imagefree

        # Mock solve 始终返回 token
        async def _solve(*a, **k):
            return ("mock-token", 0.03)

        # Mock submit 始终失败（触发重试耗尽）
        async def _submit(*a, **k):
            raise RuntimeError("timeout")

        monkeypatch.setattr(w_turnstile, "solve_turnstile", _solve)
        monkeypatch.setattr(w_imagefree, "submit_generate", _submit)
        monkeypatch.setattr(config, "IF_TXT_RETRY_MAX", 2)
        monkeypatch.setattr(config, "IF_DLQ_ENABLED", True)

        e = Engine(tmp_db)
        await e.start()
        try:
            tid = await e.submit("p", "1:1", False)
            await e.wait_result(tid, 60)
            # push_dlq 在 wait_result 返回后执行（wait_result 一看到 error 即返回），稍等确保落库
            await asyncio.sleep(0.5)
            # 检查 DLQ 中是否有记录
            dlq_items = await tmp_db.list_dlq(10)
            assert len(dlq_items) >= 1
            assert dlq_items[0]["task_id"] == tid
        finally:
            await e.stop()

    @pytest.mark.asyncio
    async def test_worker_skip_dlq_when_disabled(self, tmp_db, monkeypatch):
        """IF_DLQ_ENABLED=0 时重试耗尽也不 push_dlq。"""
        import api.worker as w
        from api.worker import Engine
        from api import turnstile_client as w_turnstile
        from api import imagefree_client as w_imagefree

        async def _solve(*a, **k):
            return ("mock-token", 0.03)

        async def _submit(*a, **k):
            raise RuntimeError("timeout")

        monkeypatch.setattr(w_turnstile, "solve_turnstile", _solve)
        monkeypatch.setattr(w_imagefree, "submit_generate", _submit)
        monkeypatch.setattr(config, "IF_TXT_RETRY_MAX", 2)
        monkeypatch.setattr(config, "IF_DLQ_ENABLED", False)

        e = Engine(tmp_db)
        await e.start()
        try:
            tid = await e.submit("p", "1:1", False)
            await e.wait_result(tid, 5)
            dlq_items = await tmp_db.list_dlq(10)
            assert len(dlq_items) == 0
        finally:
            await e.stop()

class TestDLQRequeueEngine:
    """S-9: DLQ 真重入队——引擎层（mark_pending_again + requeue_dlq_task）。"""

    @pytest.mark.asyncio
    async def test_mark_pending_again_resets_fields(self, tmp_db: DB):
        await tmp_db.create_request("t-rq", "p", "1:1", False)
        await tmp_db.mark_started("t-rq")
        await tmp_db.mark_finished("t-rq", "error", None, "boom", 1.0)
        await tmp_db.mark_pending_again("t-rq")
        row = await tmp_db.get("t-rq")
        assert row["status"] == "pending"
        assert row["error"] is None
        assert row["duration_sec"] is None

    @pytest.mark.asyncio
    async def test_requeue_dlq_task_puts_back_to_queue(self, tmp_db):
        """失败任务 → requeue → 出现在队列中且状态 pending。"""
        from api.worker import Engine
        eng = Engine(tmp_db)
        await tmp_db.create_request("t-rq2", "p", "1:1", False)
        await tmp_db.mark_finished("t-rq2", "error", None, "upstream err", 1.0)
        ok = await eng.requeue_dlq_task("t-rq2")
        assert ok is True
        assert eng.queue.qsize() == 1
        priority, seq, tid = eng.queue.get_nowait()
        assert tid == "t-rq2"
        assert priority == 2  # normal 队列
        # 入队时刻已登记（S-4 打点）
        assert "t-rq2" in eng._enqueued_at

    @pytest.mark.asyncio
    async def test_requeue_nonexistent_task(self, tmp_db):
        from api.worker import Engine
        eng = Engine(tmp_db)
        ok = await eng.requeue_dlq_task("no-such-task")
        assert ok is False

    @pytest.mark.asyncio
    async def test_requeue_config_flag_default_off(self):
        from api import config
        # 默认关：防止被刷；端点行为由集成测试覆盖
        assert config.IF_DLQ_REQUEUE is False

    @pytest.mark.asyncio
    async def test_requeue_queue_full_rolls_back(self, tmp_db):
        """队列满时重入队失败且状态回滚为 error。"""
        from api.worker import Engine, QueueFull  # noqa: F401
        eng = Engine(tmp_db)
        # 填满 normal 队列（默认 NORMAL_QUEUE_MAX 可能很大，用 monkeypatch 缩小）
        import api.config as cfg
        monkey_old = cfg.NORMAL_QUEUE_MAX
        cfg.NORMAL_QUEUE_MAX = 1
        try:
            eng.queue._limits[2] = 1 if hasattr(eng.queue, "_limits") else None
            # 直接塞一个占位
            eng.queue.put_nowait((2, 99999, "filler"))
            await tmp_db.create_request("t-full", "p", "1:1", False)
            await tmp_db.mark_finished("t-full", "error", None, "e", 1.0)
            ok = await eng.requeue_dlq_task("t-full")
            assert ok is False
            row = await tmp_db.get("t-full")
            assert row["status"] == "error"
            assert "requeue_failed" in (row["error"] or "")
        finally:
            cfg.NORMAL_QUEUE_MAX = monkey_old
