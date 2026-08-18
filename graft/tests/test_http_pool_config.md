# tests/test_http_pool_config.py

- TestHttpPoolConfig · class · L22-L52 — class TestHttpPoolConfig
- test_defaults_are_correct · method · L25-L37 — def test_defaults_are_correct(self)
- test_env_overrides · method · L39-L52 — def test_env_overrides(self, monkeypatch)
- TestTurnstileClientPoolConfig · class · L55-L84 — class TestTurnstileClientPoolConfig
- _get_pool · method · L59-L64 — def _get_pool(client)
- test_pool_limits_use_config · method · L67-L84 — async def test_pool_limits_use_config(self, monkeypatch)
- TestImagefreeClientPoolConfig · class · L87-L114 — class TestImagefreeClientPoolConfig
- _get_pool · method · L91-L96 — def _get_pool(client)
- test_pool_limits_use_config · method · L99-L114 — async def test_pool_limits_use_config(self, monkeypatch)
- TestSemaphoreManager · class · L117-L175 — class TestSemaphoreManager
- test_default_semaphore_value · method · L120-L128 — def test_default_semaphore_value(self, monkeypatch)
- test_acquire_and_release · method · L131-L139 — async def test_acquire_and_release(self)
- test_semaphore_limits_concurrency · method · L142-L175 — async def test_semaphore_limits_concurrency(self, monkeypatch)
