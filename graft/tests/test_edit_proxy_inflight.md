# tests/test_edit_proxy_inflight.py

- TestEditProxyPoolInflight · class · L17-L102 — class TestEditProxyPoolInflight
- test_acquire_proxy_is_async · method · L21-L26 — async def test_acquire_proxy_is_async(self)
- test_sem_inflight_limits_concurrency · method · L29-L52 — async def test_sem_inflight_limits_concurrency(self, monkeypatch)
- test_release_proxy_releases_semaphore · method · L55-L67 — async def test_release_proxy_releases_semaphore(self, monkeypatch)
- test_pool_disabled_no_semaphore_limit · method · L70-L78 — async def test_pool_disabled_no_semaphore_limit(self)
- test_release_proxy_with_none · method · L81-L84 — async def test_release_proxy_with_none(self)
- test_round_robin_with_semaphore · method · L87-L102 — async def test_round_robin_with_semaphore(self, monkeypatch)
