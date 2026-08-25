"""SQLite 租约锁（Lease Lock）单元测试。"""
import asyncio
import os
import tempfile
import time

import pytest

from api.db.lease_store import LeaseStore


@pytest.fixture
def store():
    path = tempfile.mktemp(suffix=".db")
    s = LeaseStore(path)
    yield s
    asyncio.get_event_loop().run_until_complete(s.close())


class TestLeaseStore:
    @pytest.mark.asyncio
    async def test_acquire_exclusive(self, store):
        ok1 = await store.acquire("key-a", "holder-1", "tok-1", ttl=30)
        assert ok1 is True
        ok2 = await store.acquire("key-a", "holder-2", "tok-2", ttl=30)
        assert ok2 is False  # 被占用

    @pytest.mark.asyncio
    async def test_expired_lock_taken_over(self, store):
        await store.acquire("key-b", "holder-1", "tok-1", ttl=-1)  # 立即过期
        ok2 = await store.acquire("key-b", "holder-2", "tok-2", ttl=30)
        assert ok2 is True

    @pytest.mark.asyncio
    async def test_release_by_token(self, store):
        await store.acquire("key-c", "holder-1", "tok-1", ttl=30)
        released = await store.release("key-c", "tok-1")
        assert released is True
        ok2 = await store.acquire("key-c", "holder-2", "tok-2", ttl=30)
        assert ok2 is True

    @pytest.mark.asyncio
    async def test_wrong_token_cannot_release(self, store):
        await store.acquire("key-d", "holder-1", "tok-1", ttl=30)
        released = await store.release("key-d", "wrong-token")
        assert released is False
        ok2 = await store.acquire("key-d", "holder-2", "tok-2", ttl=30)
        assert ok2 is False  # 仍被占

    @pytest.mark.asyncio
    async def test_renew_extends_expiry(self, store):
        await store.acquire("key-e", "holder-1", "tok-1", ttl=30)
        renewed = await store.renew("key-e", "tok-1", new_ttl=30)
        assert renewed is True
        row = await store.get("key-e")
        assert row["holder"] == "holder-1"

    @pytest.mark.asyncio
    async def test_expired_lock_cannot_renew(self, store):
        """过期锁不得被旧持有者续租复活（acquire 会覆盖新锁）。"""
        await store.acquire("key-f", "holder-1", "tok-1", ttl=-1)  # 立即过期
        renewed = await store.renew("key-f", "tok-1", new_ttl=30)
        assert renewed is False

    @pytest.mark.asyncio
    async def test_acquire_after_blocked(self, store):
        """acquire 被占返回 False 后，后续 acquire 正常（事务已回滚）。"""
        ok1 = await store.acquire("key-g", "holder-1", "tok-1", ttl=30)
        assert ok1 is True
        ok2 = await store.acquire("key-g", "holder-2", "tok-2", ttl=30)
        assert ok2 is False
        # 锁仍被 holder-1/tok-1 持有，同 key 再次 acquire 不崩溃且正确返回 False
        ok3 = await store.acquire("key-g", "holder-1", "tok-1", ttl=30)
        assert ok3 is False

    @pytest.mark.asyncio
    async def test_acquire_concurrent(self, store):
        """并发争夺同一 key，仅一个成功。"""
        async def try_acquire(label):
            return await store.acquire("concurrent-key", label, f"tok-{label}", 30)

        results = await asyncio.gather(try_acquire("A"), try_acquire("B"))
        assert sum(results) == 1  # 仅一个成功

    @pytest.mark.asyncio
    async def test_reopen_after_close(self, store):
        """close 后 reopen（惰性重开）可继续使用。"""
        assert await store.acquire("key-reopen", "h1", "t1", 30) is True
        await store.close()
        assert await store.acquire("key-reopen", "h2", "t2", 30) is False  # 仍被占
        assert await store.acquire("key-reopen-2", "h2", "t2", 30) is True  # 新 key 正常

    @pytest.mark.asyncio
    async def test_close_then_acquire_new_key(self, store):
        """模拟持有结束：close 后新 key 可正常获取，不残留事务。"""
        assert await store.acquire("key-close-1", "h1", "t1", 30) is True
        await store.close()
        assert await store.acquire("key-close-2", "h2", "t2", 30) is True