# tests/test_observability.py

- TestDbCleanup · class · L12-L42 — class TestDbCleanup
- test_cleanup_deletes_old_only · method · L14-L34 — async def test_cleanup_deletes_old_only(self, tmp_db)
- test_cleanup_noop_when_nothing_old · method · L37-L42 — async def test_cleanup_noop_when_nothing_old(self, tmp_db)
- TestPublicProjection · class · L46-L65 — class TestPublicProjection
- test_get_public_excludes_prompt · method · L48-L60 — async def test_get_public_excludes_prompt(self, tmp_db)
- test_get_public_missing · method · L63-L65 — async def test_get_public_missing(self, tmp_db)
- TestMetrics · class · L69-L80 — class TestMetrics
- test_metrics_returns_prometheus_text · method · L71-L80 — async def test_metrics_returns_prometheus_text(self)
- TestHealthz · class · L84-L107 — class TestHealthz
- test_healthz_has_deep_metrics · method · L86-L94 — async def test_healthz_has_deep_metrics(self)
- test_cf_probe_cache_ttl · method · L97-L107 — async def test_cf_probe_cache_ttl(self)
- TestDiskLogger · class · L112-L153 — class TestDiskLogger
- test_setup_creates_dir_and_writes · method · L113-L136 — def test_setup_creates_dir_and_writes(self, tmp_path)
- test_teardown_removes_handler · method · L138-L144 — def test_teardown_removes_handler(self, tmp_path)
- test_rotation_keeps_backup_count · method · L146-L153 — def test_rotation_keeps_backup_count(self, tmp_path)
