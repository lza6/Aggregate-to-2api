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
    db 的打桩对象仅实现 cleanup_batched；其余后台循环都处于长 sleep，测试窗口内不会触发。
    """
    monkeypatch.setattr(bg_tasks, "_seconds_until_next_0400", lambda now: 0.05)

    class _StubDB:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        async def cleanup_batched(self, retention_days: int, batch_size: int = 5000) -> dict:
            self.calls.append((retention_days, batch_size))
            return {"deleted": 0, "batches": 0, "size_before": 0, "size_after": 0}

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
