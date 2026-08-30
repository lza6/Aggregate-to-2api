"""IMP-07: DB 索引补全测试。"""

import time

import pytest


class TestDBIndexes:
    """索引结构验证。"""

    @pytest.mark.asyncio
    async def test_created_status_index_exists(self, tmp_db):
        """idx_requests_created_status 复合索引应存在。"""
        _, conn, lock = await tmp_db._get_write_conn()
        async with lock:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_requests_created_status'"
            )
            rows = await cursor.fetchall()
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_existing_indexes_still_present(self, tmp_db):
        """原有索引仍存在。"""
        _, conn, lock = await tmp_db._get_write_conn()
        async with lock:
            cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            names = {r[0] for r in await cursor.fetchall()}
        for idx in ("idx_requests_created", "idx_requests_status", "idx_requests_finished"):
            assert idx in names, f"缺失索引: {idx}"


class TestDayMonthColumn:
    """day/month 列填充验证。"""

    @pytest.mark.asyncio
    async def test_create_request_writes_day_month(self, tmp_db):
        """create_request 写入 day 和 month 列。"""
        await tmp_db.create_request("test-day-month", "prompt", "1:1", False)
        await tmp_db.flush()
        _, conn, lock = await tmp_db._get_write_conn()
        async with lock:
            cursor = await conn.execute("SELECT day, month FROM requests WHERE id=?", ("test-day-month",))
            row = await cursor.fetchone()
        assert row is not None, "day/month 列未填充"
        assert row[0] is not None, "day 列未写入"
        assert row[1] is not None, "month 列未写入"

    @pytest.mark.asyncio
    async def test_day_month_format(self, tmp_db):
        """day 格式 YYYY-MM-DD，month 格式 YYYY-MM。"""
        await tmp_db.create_request("test-format", "prompt", "1:1", False)
        await tmp_db.flush()
        _, conn, lock = await tmp_db._get_write_conn()
        async with lock:
            cursor = await conn.execute("SELECT day, month FROM requests WHERE id=?", ("test-format",))
            row = await cursor.fetchone()
        assert row is not None
        day, month = row[0], row[1]
        assert len(day) == 10, f"day 格式异常: {day}"
        assert day[4] == "-" and day[7] == "-", f"day 格式异常: {day}"
        assert len(month) == 7, f"month 格式异常: {month}"


class TestStatsWithDayMonth:
    """使用 day/month 列的统计查询。"""

    @pytest.mark.asyncio
    async def test_stats_daily_uses_day_column(self, tmp_db):
        """stats_daily 使用 day 列查询。"""
        await tmp_db.create_request("s1", "p1", "1:1", False)
        await tmp_db.flush()
        result = await tmp_db.stats_daily(7)
        assert len(result) >= 1
        assert "day" in result[0]
        assert result[0]["total"] >= 1

    @pytest.mark.asyncio
    async def test_stats_monthly_uses_month_column(self, tmp_db):
        """stats_monthly 使用 month 列查询。"""
        await tmp_db.create_request("s2", "p2", "1:1", False)
        await tmp_db.flush()
        result = await tmp_db.stats_monthly(12)
        assert len(result) >= 1
        assert "month" in result[0]
        assert result[0]["total"] >= 1

    @pytest.mark.asyncio
    async def test_stats_daily_old_data_still_works(self, tmp_db):
        """旧数据无 day 列时 stats_daily 不报错（返回空或包含当前数据）。"""
        # 直接插入旧数据（无 day/month 列）
        _, conn, lock = await tmp_db._get_write_conn()
        async with lock:
            await conn.execute(
                "INSERT INTO requests (id, prompt, aspect_ratio, download, status, created_at, type, model)"
                " VALUES (?, ?, ?, ?, 'completed', ?, 'txt', 'default')",
                ("old-data-no-day", "old prompt", "1:1", 0, time.time()),
            )
            await conn.commit()
        result = await tmp_db.stats_daily(7)
        # 不应 crash
        assert isinstance(result, list)


class TestCleanupAnalyze:
    """cleanup 后 ANALYZE 触发。"""

    @pytest.mark.asyncio
    async def test_cleanup_runs_analyze(self, tmp_db):
        """cleanup 执行完毕不报错（含 ANALYZE）。"""
        result = await tmp_db.cleanup(365)
        assert "deleted" in result
        assert "size_before" in result
        assert "size_after" in result
