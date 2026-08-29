"""IMP-29: 持久化队列（去中心化）单元测试。

覆盖场景：
- 停服后队列持久化（任务写入 task_queue 表）
- 重启后消费（恢复 pending 任务）
- IF_PERSISTENT_QUEUE_ENABLED=0 时保持原行为
- 并发安全

注意：Engine 已接入异步 QueueStore（aiosqlite），所有 queue_db 交互为 async。
"""
import asyncio
import os
import tempfile
import threading
import time

import pytest

from api import config
from api.db import QueueDB


class TestQueueDB:
    """QueueDB（同步旧实现）基础操作验证——兼容层仍保留，确保不回归。"""

    def _make_qdb(self) -> tuple[QueueDB, str]:
        fd, path = tempfile.mkstemp(suffix=".queue.db")
        os.close(fd)
        qdb = QueueDB(path)
        return qdb, path

    def _cleanup(self, path: str) -> None:
        try:
            os.unlink(path)
            for suffix in ("-wal", "-shm"):
                if os.path.exists(path + suffix):
                    os.unlink(path + suffix)
        except OSError:
            pass

    def test_enqueue_and_list_pending(self):
        """enqueue 后 list_pending 可读取。"""
        qdb, path = self._make_qdb()
        try:
            qdb.enqueue("t1", 2, 1)
            qdb.enqueue("t2", 1, 2)
            qdb.enqueue("t3", 0, 3)

            pending = qdb.list_pending()
            assert len(pending) == 3
            # 按 priority 升序，同 priority 按 seq 升序
            assert pending == [(0, 3, "t3"), (1, 2, "t2"), (2, 1, "t1")]
        finally:
            self._cleanup(path)

    def test_mark_processing_and_completed(self):
        """mark_processing 和 mark_completed 后不再出现在 pending 中。"""
        qdb, path = self._make_qdb()
        try:
            qdb.enqueue("t1", 2, 1)
            qdb.mark_processing("t1")
            assert len(qdb.list_pending()) == 0

            qdb.enqueue("t2", 2, 2)
            qdb.mark_completed("t2")
            assert len(qdb.list_pending()) == 0
        finally:
            self._cleanup(path)

    def test_list_pending_order(self):
        """list_pending 按 priority/seq 升序。"""
        qdb, path = self._make_qdb()
        try:
            qdb.enqueue("a", 2, 5)
            qdb.enqueue("b", 0, 1)
            qdb.enqueue("c", 1, 3)
            qdb.enqueue("d", 0, 2)
            qdb.enqueue("e", 2, 4)

            pending = qdb.list_pending()
            assert [(p, s, tid) for p, s, tid in pending] == [
                (0, 1, "b"), (0, 2, "d"), (1, 3, "c"), (2, 4, "e"), (2, 5, "a"),
            ]
        finally:
            self._cleanup(path)

    def test_concurrent_enqueue(self):
        """多线程并发 enqueue 不崩溃（竞态模拟）。"""
        qdb, path = self._make_qdb()
        try:
            errors = []

            def writer(n: int):
                try:
                    for i in range(n):
                        qdb.enqueue(f"c{i}-{threading.get_ident()}", i % 3, i)
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=writer, args=(50,)) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert not errors, f"并发异常: {errors}"
            assert len(qdb.list_pending()) == 250
        finally:
            self._cleanup(path)

    def test_restore_pending_after_reopen(self):
        """关闭后重新打开，pending 任务仍可恢复。"""
        qdb, path = self._make_qdb()
        try:
            qdb.enqueue("t1", 2, 1)
            qdb.enqueue("t2", 0, 2)
            qdb.enqueue("t3", 1, 3)
            qdb.close()

            # 重新打开
            qdb2 = QueueDB(path)
            try:
                pending = qdb2.list_pending()
                assert len(pending) == 3
                assert pending == [(0, 2, "t2"), (1, 3, "t3"), (2, 1, "t1")]
            finally:
                qdb2.close()
        finally:
            self._cleanup(path)

    def test_mark_completed_removes_from_pending(self):
        """标记 completed 的任务不再出现在 pending 中。"""
        qdb, path = self._make_qdb()
        try:
            qdb.enqueue("t1", 2, 1)
            qdb.enqueue("t2", 1, 2)
            assert len(qdb.list_pending()) == 2

            qdb.mark_completed("t1")
            pending = qdb.list_pending()
            assert len(pending) == 1
            assert pending[0][2] == "t2"
        finally:
            self._cleanup(path)


class TestQueueStore:
    """QueueStore（异步 aiosqlite）基础操作验证——Engine 当前实际使用的新实现。"""

    def _make_store(self) -> tuple["QueueStore", str]:
        from api.db.queue_store import QueueStore

        fd, path = tempfile.mkstemp(suffix=".queue.db")
        os.close(fd)
        store = QueueStore(path)
        return store, path

    def _cleanup(self, path: str) -> None:
        try:
            os.unlink(path)
            for suffix in ("-wal", "-shm"):
                if os.path.exists(path + suffix):
                    os.unlink(path + suffix)
        except OSError:
            pass

    @pytest.mark.asyncio
    async def test_enqueue_and_list_pending(self):
        store, path = self._make_store()
        try:
            await store.enqueue("t1", 2, 1)
            await store.enqueue("t2", 1, 2)
            await store.enqueue("t3", 0, 3)

            pending = await store.list_pending()
            assert len(pending) == 3
            assert pending == [(0, 3, "t3"), (1, 2, "t2"), (2, 1, "t1")]
        finally:
            await store.close()
            self._cleanup(path)

    @pytest.mark.asyncio
    async def test_mark_processing_and_completed(self):
        store, path = self._make_store()
        try:
            await store.enqueue("t1", 2, 1)
            await store.mark_processing("t1")
            assert len(await store.list_pending()) == 0

            await store.enqueue("t2", 2, 2)
            await store.mark_completed("t2")
            assert len(await store.list_pending()) == 0
        finally:
            await store.close()
            self._cleanup(path)

    @pytest.mark.asyncio
    async def test_restore_pending_after_reopen(self):
        store, path = self._make_store()
        try:
            await store.enqueue("t1", 2, 1)
            await store.enqueue("t2", 0, 2)
            await store.enqueue("t3", 1, 3)
            await store.close()

            store2, _ = self._make_store()
            store2.path = path  # 复用同一 DB 文件
            try:
                pending = await store2.list_pending()
                assert len(pending) == 3
                assert pending == [(0, 2, "t2"), (1, 3, "t3"), (2, 1, "t1")]
            finally:
                await store2.close()
        finally:
            self._cleanup(path)

    @pytest.mark.asyncio
    async def test_cleanup_deletes_expired_pending(self):
        """cleanup 删除超期 pending 记录，保留未超期及新任务。"""
        store, path = self._make_store()
        try:
            await store.enqueue("old", 2, 1)
            # 直接篡改 created_at 使其超过 7 天保留期
            cutoff = time.time() - 8 * 86400
            cur = await store._conn.execute(
                "UPDATE task_queue SET created_at=? WHERE task_id='old'", (cutoff,))
            await store._conn.commit()
            assert cur.rowcount == 1
            await store.enqueue("new", 2, 2)

            res = await store.cleanup(retention_days=7)
            assert res["deleted"] == 1
            pending = await store.list_pending()
            assert [p[2] for p in pending] == ["new"]
        finally:
            await store.close()
            self._cleanup(path)


class _DBStub:
    """最小 DB 替身（同 test_priority_queue.py，async 化以匹配 DB 迁移）。"""

    def __init__(self) -> None:
        self.created: list[str] = []
        self.finished: list[str] = []
        self.tasks: dict[str, dict] = {}

    async def create_request(self, task_id, prompt, aspect_ratio, download, request_type, model,
                             client_ip=None, user_agent=None):
        self.created.append(task_id)
        self.tasks[task_id] = {
            "id": task_id, "prompt": prompt, "aspect_ratio": aspect_ratio,
            "status": "pending", "error": None,
        }

    async def mark_finished(self, task_id, status, image_url, error, duration, image_base64=None, image_mime=None):
        self.finished.append(task_id)
        if task_id in self.tasks:
            self.tasks[task_id].update(status=status, error=error)

    async def mark_started(self, task_id):
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = "processing"

    async def get(self, task_id):
        return self.tasks.get(task_id)

    async def recover_stale_tasks(self) -> int:
        return 0


class TestEnginePersistentQueueIntegration:
    """Engine 与持久化队列集成验证（QueueStore 异步接入）。"""

    @pytest.fixture
    def engine_with_persistent(self):
        """Engine 实例（mock DB，持久化队列开启）。"""
        from api.worker import Engine

        old_enabled = config.IF_PERSISTENT_QUEUE_ENABLED
        config.IF_PERSISTENT_QUEUE_ENABLED = True

        fd, qpath = tempfile.mkstemp(suffix=".queue.db")
        os.close(fd)
        old_db = config.IF_PERSISTENT_QUEUE_DB
        config.IF_PERSISTENT_QUEUE_DB = qpath

        e = Engine(_DBStub())
        e._started = False

        yield e, qpath

        config.IF_PERSISTENT_QUEUE_ENABLED = old_enabled
        config.IF_PERSISTENT_QUEUE_DB = old_db
        try:
            os.unlink(qpath)
            for suffix in ("-wal", "-shm"):
                if os.path.exists(qpath + suffix):
                    os.unlink(qpath + suffix)
        except OSError:
            pass

    @pytest.fixture
    def engine_without_persistent(self):
        """Engine 实例（mock DB，持久化队列关闭）。"""
        from api.worker import Engine

        old_enabled = config.IF_PERSISTENT_QUEUE_ENABLED
        config.IF_PERSISTENT_QUEUE_ENABLED = False

        e = Engine(_DBStub())
        e._started = False

        yield e

        config.IF_PERSISTENT_QUEUE_ENABLED = old_enabled

    @pytest.mark.asyncio
    async def test_submit_writes_queue_db(self, engine_with_persistent):
        """submit 后 task_queue 表有 pending 记录。"""
        e, qpath = engine_with_persistent
        tid = await e.submit("test prompt", "1:1", False)
        assert e._queue_db is not None
        pending = await e._queue_db.list_pending()
        assert len(pending) == 1
        assert pending[0][2] == tid

    @pytest.mark.asyncio
    async def test_submit_priority_writes_queue_db(self, engine_with_persistent):
        """submit_priority 后 task_queue 表有 pending 记录。"""
        e, qpath = engine_with_persistent
        tid = await e.submit_priority("test", "1:1", False, priority=0)
        pending = await e._queue_db.list_pending()
        assert len(pending) == 1
        assert pending[0][0] == 0  # priority
        assert pending[0][2] == tid

    @pytest.mark.asyncio
    async def test_no_write_when_disabled(self, engine_without_persistent):
        """IF_PERSISTENT_QUEUE_ENABLED=0 时不入队。"""
        e = engine_without_persistent
        await e.submit("test", "1:1", False)
        assert e._queue_db is None

    @pytest.mark.asyncio
    async def test_finish_marks_completed(self, engine_with_persistent):
        """_finish 后 task_queue 标记 completed。"""
        e, qpath = engine_with_persistent
        tid = await e.submit("test", "1:1", False)
        assert len(await e._queue_db.list_pending()) == 1

        await e._finish(tid, "completed", "https://img.url", None, time.monotonic())
        assert len(await e._queue_db.list_pending()) == 0

    @pytest.mark.asyncio
    async def test_resume_from_queue(self, engine_with_persistent):
        """_resume_from_queue 恢复 pending 任务到内存队列。"""
        e, qpath = engine_with_persistent
        # 模拟已有 pending 任务（直接写 queue_db）
        await e._queue_db.enqueue("r1", 2, 1)
        await e._queue_db.enqueue("r2", 0, 2)
        await e._queue_db.enqueue("r3", 1, 3)

        restored = await e._resume_from_queue()
        assert restored == 3
        assert e.queue.qsize() == 3
        # 验证优先级/seq 顺序
        items = [e.queue.get_nowait() for _ in range(3)]
        assert items[0] == (0, 2, "r2")
        assert items[1] == (1, 3, "r3")
        assert items[2] == (2, 1, "r1")

    @pytest.mark.asyncio
    async def test_persistent_queue_restart_recovery(self, engine_with_persistent):
        """模拟停服重启：队列 DB 中的 pending 可被新 Engine 恢复。"""
        from api.worker import Engine
        from api.db.queue_store import QueueStore

        e, qpath = engine_with_persistent
        # 写入任务
        tid0 = await e.submit_priority("task1", "1:1", False, priority=0)
        tid2 = await e.submit_priority("task2", "1:1", False, priority=2)
        tid1 = await e.submit_priority("task3", "1:1", False, priority=1)
        # 消费一个（标记 completed）
        await e._finish(tid0, "completed", "https://img.url", None, time.monotonic())
        # 关闭
        await e._queue_db.close()

        # 新 Engine 从同一 DB 恢复
        e2 = Engine(_DBStub())
        e2._started = False
        e2._persistent_queue = True
        e2._queue_db = QueueStore(qpath)

        restored = await e2._resume_from_queue()
        assert restored == 2, "应恢复 2 个未消费任务"
        # 验证内存队列中任务按 priority 排序
        items = [e2.queue.get_nowait() for _ in range(2)]
        # task3 (p=1) 先于 task2 (p=2)
        assert items[0][0] == 1
        assert items[0][2] == tid1
        assert items[1][0] == 2
        assert items[1][2] == tid2

        await e2._queue_db.close()

    @pytest.mark.asyncio
    async def test_restore_preserves_order(self, engine_with_persistent):
        """恢复时按 priority/seq 正确排序。"""
        e, qpath = engine_with_persistent
        # 乱序写入 queue_db
        await e._queue_db.enqueue("a", 2, 5)
        await e._queue_db.enqueue("b", 0, 3)
        await e._queue_db.enqueue("c", 1, 1)
        await e._queue_db.enqueue("d", 0, 2)
        await e._queue_db.enqueue("e", 2, 4)

        pending = await e._queue_db.list_pending()
        assert [(p, s, tid) for p, s, tid in pending] == [
            (0, 2, "d"), (0, 3, "b"), (1, 1, "c"), (2, 4, "e"), (2, 5, "a"),
        ]

        restored = await e._resume_from_queue()
        assert restored == 5

        # 消费顺序验证
        items = [e.queue.get_nowait() for _ in range(5)]
        assert items[0] == (0, 2, "d")
        assert items[1] == (0, 3, "b")
        assert items[2] == (1, 1, "c")
        assert items[3] == (2, 4, "e")
        assert items[4] == (2, 5, "a")

    @pytest.mark.asyncio
    async def test_persistent_queue_marks_processing_in_process(self, engine_with_persistent):
        """mark_processing 后 pending 应减少（QueueStore 异步）。"""
        e, qpath = engine_with_persistent
        tid = await e.submit("test", "1:1", False)
        pending = await e._queue_db.list_pending()
        assert len(pending) == 1
        assert pending[0][2] == tid

        await e._queue_db.mark_processing(tid)
        assert len(await e._queue_db.list_pending()) == 0