# tests/test_observability.py

- TestDbCleanup · class · L12-L37 — class TestDbCleanup
- test_cleanup_deletes_old_only · method · L13-L30 — def test_cleanup_deletes_old_only(self, tmp_db)
- test_cleanup_noop_when_nothing_old · method · L32-L37 — def test_cleanup_noop_when_nothing_old(self, tmp_db)
- TestPublicProjection · class · L41-L57 — class TestPublicProjection
- test_get_public_excludes_prompt · method · L42-L54 — def test_get_public_excludes_prompt(self, tmp_db)
- test_get_public_missing · method · L56-L57 — def test_get_public_missing(self, tmp_db)
- TestMetrics · class · L61-L72 — class TestMetrics
- test_metrics_returns_prometheus_text · method · L63-L72 — async def test_metrics_returns_prometheus_text(self)
- TestHealthz · class · L76-L98 — class TestHealthz
- test_healthz_has_deep_metrics · method · L78-L86 — async def test_healthz_has_deep_metrics(self)
- test_cf_probe_cache_ttl · method · L89-L98 — async def test_cf_probe_cache_ttl(self)
