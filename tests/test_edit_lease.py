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