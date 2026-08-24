# tests/test_observability.py

- TestDbCleanup · class · L12-L42 — class TestDbCleanup
- test_cleanup_deletes_old_only · method · L14-L34 — async def test_cleanup_deletes_old_only(self, tmp_db)
- test_cleanup_noop_when_nothing_old · method · L37-L42 — async def test_cleanup_noop_when_nothing_old(self, tmp_db)
- TestPublicProjection · class · L46-L65 — class TestPublicProjection
- test_get_public_excludes_prompt · method · L48-L60 — async def test_get_public_excludes_prompt(self, tmp_db)
- test_get_public_missing · method · L63-L65 — async def test_get_public_missing(self, tmp_db)
- TestMetrics · class · L69-L80 — class TestMetrics
- test_metrics_returns_prometheus_text · method · L71-L80 — async def test_metrics_returns_prometheus_text(self)
- TestHealthz · class · L84-L106 — class TestHealthz
- test_healthz_has_deep_metrics · method · L86-L94 — async def test_healthz_has_deep_metrics(self)
- test_cf_probe_cache_ttl · method · L97-L106 — async def test_cf_probe_cache_ttl(self)
- TestDiskLogger · class · L111-L152 — class TestDiskLogger
- test_setup_creates_dir_and_writes · method · L112-L135 — def test_setup_creates_dir_and_writes(self, tmp_path)
- test_teardown_removes_handler · method · L137-L143 — def test_teardown_removes_handler(self, tmp_path)
- test_rotation_keeps_backup_count · method · L145-L152 — def test_rotation_keeps_backup_count(self, tmp_path)
