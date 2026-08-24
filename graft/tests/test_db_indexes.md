# tests/test_db_indexes.py

- TestDBIndexes · class · L9-L33 — class TestDBIndexes
- test_created_status_index_exists · method · L13-L21 — async def test_created_status_index_exists(self, tmp_db)
- test_existing_indexes_still_present · method · L24-L33 — async def test_existing_indexes_still_present(self, tmp_db)
- TestDayMonthColumn · class · L36-L69 — class TestDayMonthColumn
- test_create_request_writes_day_month · method · L40-L52 — async def test_create_request_writes_day_month(self, tmp_db)
- test_day_month_format · method · L55-L69 — async def test_day_month_format(self, tmp_db)
- TestStatsWithDayMonth · class · L72-L109 — class TestStatsWithDayMonth
- test_stats_daily_uses_day_column · method · L76-L83 — async def test_stats_daily_uses_day_column(self, tmp_db)
- test_stats_monthly_uses_month_column · method · L86-L93 — async def test_stats_monthly_uses_month_column(self, tmp_db)
- test_stats_daily_old_data_still_works · method · L96-L109 — async def test_stats_daily_old_data_still_works(self, tmp_db)
- TestCleanupAnalyze · class · L112-L121 — class TestCleanupAnalyze
- test_cleanup_runs_analyze · method · L116-L121 — async def test_cleanup_runs_analyze(self, tmp_db)
