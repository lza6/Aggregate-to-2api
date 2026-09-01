# tests/test_db_indexes.py

- TestDBIndexes · class · L8-L30 — class TestDBIndexes
- test_created_status_index_exists · method · L12-L20 — async def test_created_status_index_exists(self, tmp_db)
- test_existing_indexes_still_present · method · L23-L30 — async def test_existing_indexes_still_present(self, tmp_db)
- TestDayMonthColumn · class · L33-L62 — class TestDayMonthColumn
- test_create_request_writes_day_month · method · L37-L47 — async def test_create_request_writes_day_month(self, tmp_db)
- test_day_month_format · method · L50-L62 — async def test_day_month_format(self, tmp_db)
- TestStatsWithDayMonth · class · L65-L102 — class TestStatsWithDayMonth
- test_stats_daily_uses_day_column · method · L69-L76 — async def test_stats_daily_uses_day_column(self, tmp_db)
- test_stats_monthly_uses_month_column · method · L79-L86 — async def test_stats_monthly_uses_month_column(self, tmp_db)
- test_stats_daily_old_data_still_works · method · L89-L102 — async def test_stats_daily_old_data_still_works(self, tmp_db)
- TestCleanupAnalyze · class · L105-L114 — class TestCleanupAnalyze
- test_cleanup_runs_analyze · method · L109-L114 — async def test_cleanup_runs_analyze(self, tmp_db)
