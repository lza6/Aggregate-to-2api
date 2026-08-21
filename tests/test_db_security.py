"""P-TEST-A4 追加: api/db.py 读写分离与安全分支补充测试。

覆盖（追加到既有 test_db_* 系列之外的特征测试）：
- list_tasks 排序白名单（非法 sort 回退 created_at；LIMIT 注入无效果）
- get_base64_path（file:// 前缀剥离 / raw base64 返回 None / 不存在任务 None）
- cleanup（删除超期记录 + 返回 size 统计）
"""
import time

import pytest

from api.db import DB


@pytest.fixture
async def db(tmp_path):
    d = DB(str(tmp_path / "t.db"))
    await d._ensure_initialized()
    yield d
    await d.close()


async def _mk_task(d: DB, i: int, delay: float = 0.0) -> str:
    """用正式 API 建任务，再补终态字段（finished/duration/model 已含）。"""
    tid = f"task-{i}"
    await d.create_request(tid, f"p{i}", "1:1", False, model="imagefree/default")
    await d.mark_finished(tid, "completed", f"https://x/{i}.png", None, 1.5)
    return tid


class TestListTasksSortWhitelist:
    @pytest.mark.asyncio
    async def test_valid_sort_created_at(self, db):
        await _mk_task(db, 1)
        items, total = await db.list_tasks(sort="created_at")
        assert total == 1

    @pytest.mark.asyncio
    async def test_invalid_sort_falls_back(self, db):
        await _mk_task(db, 1)
        # 非法 sort 不抛异常，回退 created_at
        items, total = await db.list_tasks(sort="created_at; DROP TABLE requests;--")
        assert total == 1
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_limit_type_enforced(self, db):
        for i in range(3):
            await _mk_task(db, i)
        # limit 走参数绑定，字符串注入类型不匹配 → sqlite 报错（不执行注入语义）
        with pytest.raises(Exception):
            await db.list_tasks(limit="1; DROP TABLE requests")
        # 表还在
        _, total = await db.list_tasks()
        assert total == 3

    @pytest.mark.asyncio
    async def test_status_filter(self, db):
        await _mk_task(db, 1)
        t2 = await _mk_task(db, 2)
        await d_flush_error(db, t2)
        _, total = await db.list_tasks(status="completed")
        assert total == 1


async def d_flush_error(d: DB, tid: str) -> None:
    await d.mark_finished(tid, "error", None, "mock-error", 0.1)


class TestGetBase64Path:
    @pytest.mark.asyncio
    async def test_file_prefix_stripped(self, db):
        tid = await _mk_task(db, 1)
        await db._enqueue_write(
            "UPDATE requests SET image_base64=? WHERE id=?",
            ("file:///data/imgs/x.b64", tid))
        await db.flush()
        path = await db.get_base64_path(tid)
        assert path == "/data/imgs/x.b64"

    @pytest.mark.asyncio
    async def test_raw_base64_returns_none(self, db):
        tid = await _mk_task(db, 1)
        await db._enqueue_write(
            "UPDATE requests SET image_base64=? WHERE id=?",
            ("iVBORw0KGgo=", tid))
        await db.flush()
        assert await db.get_base64_path(tid) is None

    @pytest.mark.asyncio
    async def test_missing_task_returns_none(self, db):
        assert await db.get_base64_path("no-such-id") is None

    @pytest.mark.asyncio
    async def test_empty_value_returns_none(self, db):
        tid = await _mk_task(db, 1)
        assert await db.get_base64_path(tid) is None


class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_deletes_expired(self, db):
        # 两条超期（40 天前）+ 一条新
        tid1 = await _mk_task(db, 1)
        await db._enqueue_write(
            "UPDATE requests SET created_at=? WHERE id=?", (time.time() - 40 * 86400, tid1))
        tid2 = await _mk_task(db, 2)
        await db._enqueue_write(
            "UPDATE requests SET created_at=? WHERE id=?", (time.time() - 40 * 86400, tid2))
        await _mk_task(db, 3)
        await db.flush()
        r = await db.cleanup(retention_days=30)
        assert r["deleted"] == 2
        assert r["size_before"] >= 0 and r["size_after"] >= 0
        _, total = await db.list_tasks()
        assert total == 1

    @pytest.mark.asyncio
    async def test_cleanup_nothing_to_delete(self, db):
        await _mk_task(db, 1)
        r = await db.cleanup(retention_days=365)
        assert r["deleted"] == 0
