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

    def test_push_and_list_dlq(self, tmp_db: DB):
        """push_dlq 后 list_dlq 应返回记录。"""
        tmp_db.push_dlq("task-001", "default", "timeout", 3)
        items = tmp_db.list_dlq(10)
        assert len(items) == 1
        assert items[0]["task_id"] == "task-001"
        assert items[0]["error"] == "timeout"
        assert items[0]["attempts"] == 3

    def test_list_dlq_limit(self, tmp_db: DB):
        """list_dlq 应遵守 limit 参数。"""
        for i in range(5):
            tmp_db.push_dlq(f"task-{i:03d}", "default", f"error-{i}", 2)
        items = tmp_db.list_dlq(3)
        assert len(items) == 3

    def test_list_dlq_ordered_by_created_at(self, tmp_db: DB):
        """list_dlq 应按 created_at 降序排列。"""
        import time
        for i in range(3):
            tmp_db.push_dlq(f"task-{i:03d}", "default", "err", 2)
            time.sleep(0.01)  # 确保时间戳不同
        items = tmp_db.list_dlq(10)
        assert len(items) == 3
        # 最新插入的应在最前
        assert items[0]["task_id"] == "task-002"
        assert items[2]["task_id"] == "task-000"

    def test_retry_dlq(self, tmp_db: DB):
        """retry_dlq 应删除指定记录。"""
        tmp_db.push_dlq("task-001", "default", "timeout", 3)
        tmp_db.retry_dlq("task-001")
        items = tmp_db.list_dlq(10)
        assert len(items) == 0

    def test_clear_dlq(self, tmp_db: DB):
        """clear_dlq 应清空所有记录。"""
        for i in range(3):
            tmp_db.push_dlq(f"task-{i:03d}", "default", "error", 2)
        tmp_db.clear_dlq()
        items = tmp_db.list_dlq(10)
        assert len(items) == 0

    def test_retry_nonexistent(self, tmp_db: DB):
        """retry_dlq 不存在的 id 不应抛异常。"""
        tmp_db.retry_dlq("nonexistent")  # 不应抛异常

    def test_clear_empty(self, tmp_db: DB):
        """clear_dlq 空表不应抛异常。"""
        tmp_db.clear_dlq()  # 不应抛异常

    def test_push_dlq_duplicate_task_id(self, tmp_db: DB):
        """同一 task_id 重复 push 应更新（OR REPLACE）。"""
        tmp_db.push_dlq("task-001", "default", "timeout", 3)
        tmp_db.push_dlq("task-001", "anime", "connection reset", 4)
        items = tmp_db.list_dlq(10)
        assert len(items) == 1
        assert items[0]["model"] == "anime"
        assert items[0]["error"] == "connection reset"
        assert items[0]["attempts"] == 4


class TestDeadLetterQueueWorker:
    """worker 层 DLQ 推送测试。"""

    @pytest.mark.asyncio
    async def test_worker_pushes_dlq_on_retry_exhaustion(self, tmp_db, monkeypatch):
        """worker 重试满后应 push_dlq。"""
        import api.worker as w
        from api.worker import Engine

        # Mock solve 始终返回 token
        async def _solve(*a, **k):
            return ("mock-token", 0.03)

        # Mock submit 始终失败（触发重试耗尽）
        async def _submit(*a, **k):
            raise RuntimeError("timeout")

        monkeypatch.setattr(w.turnstile_client, "solve_turnstile", _solve)
        monkeypatch.setattr(w.imagefree_client, "submit_generate", _submit)
        monkeypatch.setattr(config, "IF_TXT_RETRY_MAX", 2)
        monkeypatch.setattr(config, "IF_DLQ_ENABLED", True)

        e = Engine(tmp_db)
        await e.start()
        try:
            tid = await e.submit("p", "1:1", False)
            await e.wait_result(tid, 5)
            # 检查 DLQ 中是否有记录
            dlq_items = tmp_db.list_dlq(10)
            assert len(dlq_items) >= 1
            assert dlq_items[0]["task_id"] == tid
        finally:
            await e.stop()

    @pytest.mark.asyncio
    async def test_worker_skip_dlq_when_disabled(self, tmp_db, monkeypatch):
        """IF_DLQ_ENABLED=0 时重试耗尽也不 push_dlq。"""
        import api.worker as w
        from api.worker import Engine

        async def _solve(*a, **k):
            return ("mock-token", 0.03)

        async def _submit(*a, **k):
            raise RuntimeError("timeout")

        monkeypatch.setattr(w.turnstile_client, "solve_turnstile", _solve)
        monkeypatch.setattr(w.imagefree_client, "submit_generate", _submit)
        monkeypatch.setattr(config, "IF_TXT_RETRY_MAX", 2)
        monkeypatch.setattr(config, "IF_DLQ_ENABLED", False)

        e = Engine(tmp_db)
        await e.start()
        try:
            tid = await e.submit("p", "1:1", False)
            await e.wait_result(tid, 5)
            dlq_items = tmp_db.list_dlq(10)
            assert len(dlq_items) == 0
        finally:
            await e.stop()