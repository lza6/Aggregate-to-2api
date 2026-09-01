# tests/test_observability.py

- TestDbCleanup · class · L9-L39 — class TestDbCleanup
- test_cleanup_deletes_old_only · method · L11-L31 — async def test_cleanup_deletes_old_only(self, tmp_db)
- test_cleanup_noop_when_nothing_old · method · L34-L39 — async def test_cleanup_noop_when_nothing_old(self, tmp_db)
- TestPublicProjection · class · L43-L62 — class TestPublicProjection
- test_get_public_excludes_prompt · method · L45-L57 — async def test_get_public_excludes_prompt(self, tmp_db)
- test_get_public_missing · method · L60-L62 — async def test_get_public_missing(self, tmp_db)
- TestMetrics · class · L66-L77 — class TestMetrics
- test_metrics_returns_prometheus_text · method · L68-L77 — async def test_metrics_returns_prometheus_text(self)
- TestHealthz · class · L81-L104 — class TestHealthz
- test_healthz_has_deep_metrics · method · L83-L91 — async def test_healthz_has_deep_metrics(self)
- test_cf_probe_cache_ttl · method · L94-L104 — async def test_cf_probe_cache_ttl(self)
- TestDiskLogger · class · L110-L156 — class TestDiskLogger
- test_setup_creates_dir_and_writes · method · L111-L137 — def test_setup_creates_dir_and_writes(self, tmp_path)
- test_teardown_removes_handler · method · L139-L146 — def test_teardown_removes_handler(self, tmp_path)
- test_rotation_keeps_backup_count · method · L148-L156 — def test_rotation_keeps_backup_count(self, tmp_path)
