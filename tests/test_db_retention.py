"""P3-2: DB 每日 04:00 分批巡检（_retention_loop + cleanup_batched）单元测试。

覆盖：
- `_seconds_until_next_0400`：只在本地 04:00 触发的纯函数计时逻辑（注入 now，无真实 sleep）。
- `_retention_loop`：通过 TaskGroup 触发一次，验证 `db.cleanup_batched` 被调用且间隔被驱动。
- `db.cleanup_batched`：向 tmp_db 塞旧数据验证分批 DELETE + VACUUM ANALYZE、批次计数、无残留。

风格参照 tests/test_persistent_queue.py：纯函数 + 依赖注入，避免真实长 sleep。
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import time

import pytest

from api import bg_tasks, config


# ── 纯函数：距下一个本地 04:00 秒数 ──────────────────────────────
def test_seconds_until_next_0400_morning_before():
    """凌晨 03:00 → 距当天 04:00 为 3600s。"""
    now = datetime.datetime(2026, 8, 31, 3, 0, 0)
    assert bg_tasks._seconds_until_next_0400(now) == 3600.0


def test_seconds_until_next_0400_after_0400():
    """04:30 → 距次日 04:00 为 23.5h（84600s）。"""
    now = datetime.datetime(2026, 8, 31, 4, 30, 0)
    assert bg_tasks._seconds_until_next_0400(now) == 23.5 * 3600


def test_seconds_until_next_0400_exact_0400():
    """恰在 04:00:00 → 视为刚过去，距次日 04:00 为 86400s。"""
    now = datetime.datetime(2026, 8, 31, 4, 0, 0)
    assert bg_tasks._seconds_until_next_0400(now) == 86400.0


def test_seconds_until_next_0400_late_night():
    """深夜 23:00 → 距次日 04:00 为 5h（18000s）。"""
    now = datetime.datetime(2026, 8, 31, 23, 0, 0)
    assert bg_tasks._seconds_until_next_0400(now) == 5 * 3600


def test_seconds_until_next_0400_midnight():
    """00:00 → 距当天 04:00 为 4h（14400s）。"""
    now = datetime.datetime(2026, 8, 31, 0, 0, 0)
    assert bg_tasks._seconds_until_next_0400(now) == 4 * 3600


def test_seconds_until_next_0400_cross_day():
    """跨天边界：03:59:59 → 距 04:00 整为 1s；只差微秒也归到下个 04:00（非负）。"""
    now = datetime.datetime(2026, 8, 31, 3, 59, 59)
    assert bg_tasks._seconds_until_next_0400(now) == 1.0


@pytest.mark.asyncio
async def test_retention_loop_triggers_cleanup_batched(monkeypatch):
    """TaskGroup 触发一次 _retention_loop：仅每日 04:00 后清理，且调用 db.cleanup_batched。

    注入：_seconds_until_next_0400 -> 0.05s（快速驱动，避免真实等到 04:00）；
    db 的打桩对象仅实现 cleanup_batched/archive_tasks；其余后台循环都处于长 sleep，
    测试窗口内不会触发。
    """
    monkeypatch.setattr(bg_tasks, "_seconds_until_next_0400", lambda now: 0.05)

    class _StubDB:
        def __init__(self) -> None:
            self.calls: list[tuple] = []
            self.archive_calls: list[int] = []

        async def cleanup_batched(self, retention_days: int, batch_size: int = 5000) -> dict:
            self.calls.append((retention_days, batch_size))
            return {"deleted": 0, "batches": 0, "size_before": 0, "size_after": 0}

        async def archive_tasks(self, older_than_days: int) -> int:
            self.archive_calls.append(older_than_days)
            return 0

    stub = _StubDB()
    task = asyncio.create_task(
        bg_tasks.run_background_tasks(stub, None, None, None, None, None)
    )
    try:
        for _ in range(100):
            if stub.calls:
                break
            await asyncio.sleep(0.02)
        assert stub.calls, "_retention_loop 未调用 db.cleanup_batched"
        retention_days, batch_size = stub.calls[0]
        # 应使用配置的 DB_RETENTION_DAYS，且默认 5000 分批
        assert retention_days == config.DB_RETENTION_DAYS
        assert batch_size == 5000
        # P1-8：软归档先于物理清理执行，且使用 IF_TASK_RETENTION_DAYS
        assert stub.archive_calls, "_retention_loop 未调用 db.archive_tasks（软归档）"
        assert stub.archive_calls[0] == config.IF_TASK_RETENTION_DAYS
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


# ── 分批清理（cleanup_batched）真实 DB 行为 ─────────────────────
@pytest.mark.asyncio
async def test_cleanup_batched_batches(tmp_db):
    """向 tmp_db 塞 12000 条超期 + 10 条新鲜记录。

    调用 cleanup_batched(retention_days=7, batch_size=5000)：
    - deleted == 12000（全部超期行删除）
    - batches == 3（首两批各 5000，第三批 2000）
    - 残留 == 10（新鲜行保留，无超期残留）
    """
    from api import config

    old_ts = time.time() - 3650 * 86400  # 10 年前，远早于 retention 7 天 cutoff
    new_ts = time.time()

    _, conn, conn_lock = await tmp_db._get_write_conn()
    async with conn_lock:
        await conn.execute("BEGIN")
        for i in range(12000):
            await conn.execute(
                "INSERT INTO requests (id, created_at) VALUES (?, ?)", (f"old-{i}", old_ts)
            )
        for i in range(10):
            await conn.execute(
                "INSERT INTO requests (id, created_at) VALUES (?, ?)", (f"new-{i}", new_ts)
            )
        await conn.commit()

    result = await tmp_db.cleanup_batched(retention_days=7, batch_size=5000)

    assert result["deleted"] == 12000
    assert result["batches"] == 3
    assert result["size_before"] >= 0
    assert result["size_after"] >= 0

    # 残留行只有 10 条新鲜记录
    count_rows = await tmp_db._get_read_conn()
    cur = await count_rows.execute("SELECT COUNT(*) FROM requests")
    row = await cur.fetchone()
    assert int(row[0]) == 10
    # 超期行必须清空
    cur2 = await count_rows.execute(
        "SELECT COUNT(*) FROM requests WHERE created_at < ?",
        (time.time() - config.DB_RETENTION_DAYS * 86400,),
    )
    row2 = await cur2.fetchone()
    assert int(row2[0]) == 0


@pytest.mark.asyncio
async def test_cleanup_batched_single_batch_no_op(tmp_db):
    """无超期行时：deleted==0、batches==0，提前跳过循环。"""
    fresh_ts = time.time()
    _, conn, conn_lock = await tmp_db._get_write_conn()
    async with conn_lock:
        await conn.execute("BEGIN")
        for i in range(5):
            await conn.execute(
                "INSERT INTO requests (id, created_at) VALUES (?, ?)", (f"fresh-{i}", fresh_ts)
            )
        await conn.commit()

    result = await tmp_db.cleanup_batched(retention_days=7, batch_size=5000)
    assert result["deleted"] == 0
    assert result["batches"] == 0


# ── P1-8 冷热归档（archive_tasks 软归档）───────────────────────
async def _seed_terminal(tmp_db, task_id: str, status: str, finished_ago_days: float) -> None:
    """直接插一行终态任务（finished_at 设定为 N 天前 10 分钟，created_at 极旧不含糊）。"""
    old_finished = time.time() - (finished_ago_days * 86400 + 600)
    _, conn, conn_lock = await tmp_db._get_write_conn()
    async with conn_lock:
        await conn.execute(
            "INSERT INTO requests (id, status, model, created_at, finished_at, duration_sec)"
            " VALUES (?, ?, 'imagefree/default', ?, ?, 5.0)",
            (task_id, status, time.time() - 20000 * 86400, old_finished),
        )
        await conn.commit()


@pytest.mark.asyncio
async def test_archive_tasks_archives_expired_terminal(tmp_db):
    """到期终态（completed/error/failed）→ archive_tasks 软归档为 archived。

    未到期终态、非终态（pending/processing）与已归档行保持不变。
    """
    await _seed_terminal(tmp_db, "old-done", "completed", 120)  # > 90 天
    await _seed_terminal(tmp_db, "old-err", "error", 120)
    await _seed_terminal(tmp_db, "old-fail", "failed", 120)
    await _seed_terminal(tmp_db, "fresh-done", "completed", 10)  # < 90 天
    await _seed_terminal(tmp_db, "plural-hold", "pending", 120)  # 非终态（不归档）
    await _seed_terminal(tmp_db, "processing-hold", "processing", 120)  # 非终态

    archived = await tmp_db.archive_tasks(older_than_days=90)
    assert archived == 3  # 仅三条到期终态

    conn = await tmp_db._get_read_conn()
    status_map = {}
    cursor = await conn.execute(
        "SELECT id, status FROM requests WHERE id IN"
        " ('old-done','old-err','old-fail','fresh-done','plural-hold','processing-hold')"
    )
    for row in await cursor.fetchall():
        status_map[row[0]] = row[1]
    assert status_map == {
        "old-done": "archived",
        "old-err": "archived",
        "old-fail": "archived",
        "fresh-done": "completed",  # 未到期不变
        "plural-hold": "pending",  # 非终态不变
        "processing-hold": "processing",  # 非终态不变
    }


@pytest.mark.asyncio
async def test_archive_tasks_zero_or_fresh_noop(tmp_db):
    """older_than_days<=0 关闭归档返回 0；无到期终态时返回 0 且状态不变。"""
    await _seed_terminal(tmp_db, "fresh-done", "completed", 10)
    assert await tmp_db.archive_tasks(older_than_days=0) == 0
    assert await tmp_db.archive_tasks(older_than_days=90) == 0  # 未到期
    conn = await tmp_db._get_read_conn()
    cursor = await conn.execute("SELECT status FROM requests WHERE id='fresh-done'")
    row = await cursor.fetchone()
    assert row[0] == "completed"


@pytest.mark.asyncio
async def test_cleanup_batched_does_not_spare_archived(tmp_db):
    """两套并存：cleanup_batched 按 created_at 物理删除，不因 archived 豁免。

    文档化设计：软归档只负责「退出热口径」，物理空间仍由物理保留期（IF_DB_RETENTION_DAYS）
    管辖——超物理保留期的 archived 行照常被物理删除回收空间。
    """
    old_ts = time.time() - 4000 * 86400  # 远超 7 天物理保留期
    fresh_ts = time.time()
    _, conn, conn_lock = await tmp_db._get_write_conn()
    async with conn_lock:
        await conn.execute("BEGIN")
        await conn.execute(
            "INSERT INTO requests (id, status, created_at, finished_at) VALUES (?, 'archived', ?, ?)",
            ("arch-old", old_ts, old_ts),
        )
        await conn.execute(
            "INSERT INTO requests (id, status, created_at, finished_at) VALUES (?, 'completed', ?, ?)",
            ("done-fresh", fresh_ts, fresh_ts),
        )
        await conn.commit()

    result = await tmp_db.cleanup_batched(retention_days=7, batch_size=5000)
    assert result["deleted"] == 1  # 只删超物理期的 archived 行
    conn2 = await tmp_db._get_read_conn()
    cursor = await conn2.execute("SELECT COUNT(*) FROM requests WHERE id='arch-old'")
    assert int((await cursor.fetchone())[0]) == 0
    cursor2 = await conn2.execute("SELECT COUNT(*) FROM requests WHERE id='done-fresh'")
    assert int((await cursor2.fetchone())[0]) == 1


@pytest.mark.asyncio
async def test_list_tasks_and_gallery_exclude_archived_by_default(tmp_db):
    """列表默认过滤 archived：list_tasks/gallery_list 退冷，显式 status='archived' 可查。"""
    now = time.time()
    _, conn, conn_lock = await tmp_db._get_write_conn()
    async with conn_lock:
        await conn.execute("BEGIN")
        rows = [
            ("arch1", "archived", "completed/p", None, now, 1000.0),
            ("live1", "completed", "live/p", "mock://img", now, 1001.0),
            ("err1", "error", "err/p", None, now, 1002.0),
        ]
        for tid, status, model, img, created, finished in rows:
            await conn.execute(
                "INSERT INTO requests (id, status, model, image_url, created_at, finished_at, prompt)"
                " VALUES (?, ?, ?, ?, ?, ?, 'p')",
                (tid, status, model, img, created, finished),
            )
        await conn.commit()

    items, total = await tmp_db.list_tasks()
    ids = {i["id"] for i in items}
    assert total == 2 and ids == {"live1", "err1"}  # archived 默认隐藏

    # 显式 status='archived' → 冷历史可查
    arch_items, arch_total = await tmp_db.list_tasks(status="archived")
    assert arch_total == 1 and arch_items[0]["id"] == "arch1"

    # gallery_list 同样退冷（且只有有图行）
    g_items, g_total = await tmp_db.gallery_list()
    assert g_total == 1 and g_items[0]["id"] == "live1"

    # 详情仍可查（gallery_get 只排除 deleted，保留 archived 可见）
    detail = await tmp_db.gallery_get("arch1")
    assert detail is not None and detail["status"] == "archived"

    # 热统计不含 archived
    ov = await tmp_db.stats_overview()
    assert ov["total_requests"] == 2 and ov["total_images"] == 1
