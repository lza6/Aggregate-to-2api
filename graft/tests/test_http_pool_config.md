# tests/test_http_pool_config.py

- TestHttpPoolConfig · class · L22-L59 — class TestHttpPoolConfig
- test_defaults_are_correct · method · L25-L44 — def test_defaults_are_correct(self)
- test_env_overrides · method · L46-L59 — def test_env_overrides(self, monkeypatch)
- TestTurnstileClientPoolConfig · class · L62-L91 — class TestTurnstileClientPoolConfig
- _get_pool · method · L66-L71 — def _get_pool(client)
- test_pool_limits_use_config · method · L74-L91 — async def test_pool_limits_use_config(self, monkeypatch)
- TestImagefreeClientPoolConfig · class · L94-L121 — class TestImagefreeClientPoolConfig
- _get_pool · method · L98-L103 — def _get_pool(client)
- test_pool_limits_use_config · method · L106-L121 — async def test_pool_limits_use_config(self, monkeypatch)
- TestSemaphoreManager · class · L124-L182 — class TestSemaphoreManager
- test_default_semaphore_value · method · L127-L135 — def test_default_semaphore_value(self, monkeypatch)
- test_acquire_and_release · method · L138-L146 — async def test_acquire_and_release(self)
- test_semaphore_limits_concurrency · method · L149-L182 — async def test_semaphore_limits_concurrency(self, monkeypatch)
