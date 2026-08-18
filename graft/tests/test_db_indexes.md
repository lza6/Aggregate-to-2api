# tests/test_db_indexes.py

- TestDBIndexes · class · L8-L28 — class TestDBIndexes
- test_created_status_index_exists · method · L11-L18 — def test_created_status_index_exists(self, tmp_db)
- test_existing_indexes_still_present · method · L20-L28 — def test_existing_indexes_still_present(self, tmp_db)
- TestDayMonthColumn · class · L31-L60 — class TestDayMonthColumn
- test_create_request_writes_day_month · method · L34-L45 — def test_create_request_writes_day_month(self, tmp_db)
- test_day_month_format · method · L47-L60 — def test_day_month_format(self, tmp_db)
- TestStatsWithDayMonth · class · L63-L97 — class TestStatsWithDayMonth
- test_stats_daily_uses_day_column · method · L66-L73 — def test_stats_daily_uses_day_column(self, tmp_db)
- test_stats_monthly_uses_month_column · method · L75-L82 — def test_stats_monthly_uses_month_column(self, tmp_db)
- test_stats_daily_old_data_still_works · method · L84-L97 — def test_stats_daily_old_data_still_works(self, tmp_db)
- TestCleanupAnalyze · class · L100-L108 — class TestCleanupAnalyze
- test_cleanup_runs_analyze · method · L103-L108 — def test_cleanup_runs_analyze(self, tmp_db)
