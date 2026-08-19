# tests/test_edit_proxy_inflight.py

- _import_pool_cls · function · L21-L31 — def _import_pool_cls()
- TestEditProxyPoolInflight · class · L37-L124 — class TestEditProxyPoolInflight
- test_acquire_proxy_is_async · method · L41-L46 — async def test_acquire_proxy_is_async(self)
- test_sem_inflight_limits_concurrency · method · L49-L72 — async def test_sem_inflight_limits_concurrency(self, monkeypatch)
- test_release_proxy_releases_semaphore · method · L75-L88 — async def test_release_proxy_releases_semaphore(self, monkeypatch)
- test_pool_disabled_no_semaphore_limit · method · L91-L99 — async def test_pool_disabled_no_semaphore_limit(self)
- test_release_proxy_with_none · method · L102-L105 — async def test_release_proxy_with_none(self)
- test_round_robin_with_semaphore · method · L108-L124 — async def test_round_robin_with_semaphore(self, monkeypatch)
