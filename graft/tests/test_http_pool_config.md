# tests/test_http_pool_config.py

- TestHttpPoolConfig · class · L22-L55 — class TestHttpPoolConfig
- test_defaults_are_correct · method · L25-L39 — def test_defaults_are_correct(self)
- test_env_overrides · method · L41-L55 — def test_env_overrides(self, monkeypatch)
- TestTurnstileClientPoolConfig · class · L58-L87 — class TestTurnstileClientPoolConfig
- _get_pool · method · L62-L67 — def _get_pool(client)
- test_pool_limits_use_config · method · L70-L87 — async def test_pool_limits_use_config(self, monkeypatch)
- TestImagefreeClientPoolConfig · class · L90-L117 — class TestImagefreeClientPoolConfig
- _get_pool · method · L94-L99 — def _get_pool(client)
- test_pool_limits_use_config · method · L102-L117 — async def test_pool_limits_use_config(self, monkeypatch)
- TestSemaphoreManager · class · L120-L179 — class TestSemaphoreManager
- test_default_semaphore_value · method · L123-L131 — def test_default_semaphore_value(self, monkeypatch)
- test_acquire_and_release · method · L134-L142 — async def test_acquire_and_release(self)
- test_semaphore_limits_concurrency · method · L145-L179 — async def test_semaphore_limits_concurrency(self, monkeypatch)
