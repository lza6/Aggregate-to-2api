"""持久化队列存储单元测试。"""
import asyncio
import os
import tempfile

import pytest

from api.db.queue_store import QueueStore


@pytest.fixture
def store():
    path = tempfile.mktemp(suffix=".db")
    s = QueueStore(path)
    yield s
    asyncio.get_event_loop().run_until_complete(s.close())


class TestQueueStore:
    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, store):
        await store.enqueue("task-1", 2, 1)
        await store.enqueue("task-0", 0, 2)
        pending = await store.list_pending()
        assert pending == [(0, 2, "task-0"), (2, 1, "task-1")]

    @pytest.mark.asyncio
    async def test_mark_completed(self, store):
        await store.enqueue("task-1", 2, 1)
        await store.mark_completed("task-1")
        assert await store.list_pending() == []

    @pytest.mark.asyncio
    async def test_mark_processing(self, store):
        await store.enqueue("task-1", 2, 1)
        await store.mark_processing("task-1")
        assert await store.list_pending() == []

    @pytest.mark.asyncio
    async def test_survives_reopen(self, store):
        path = store.path
        await store.enqueue("task-x", 0, 1)
        await store.close()
        store2 = QueueStore(path)
        pending = await store2.list_pending()
        assert pending == [(0, 1, "task-x")]
        await store2.close()