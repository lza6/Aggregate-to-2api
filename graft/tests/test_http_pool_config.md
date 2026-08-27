# tests/test_http_pool_config.py

- TestHttpPoolConfig · class · L21-L53 — class TestHttpPoolConfig
- test_defaults_are_correct · method · L24-L38 — def test_defaults_are_correct(self)
- test_env_overrides · method · L40-L53 — def test_env_overrides(self, monkeypatch)
- TestTurnstileClientPoolConfig · class · L56-L85 — class TestTurnstileClientPoolConfig
- _get_pool · method · L60-L65 — def _get_pool(client)
- test_pool_limits_use_config · method · L68-L85 — async def test_pool_limits_use_config(self, monkeypatch)
- TestImagefreeClientPoolConfig · class · L88-L115 — class TestImagefreeClientPoolConfig
- _get_pool · method · L92-L97 — def _get_pool(client)
- test_pool_limits_use_config · method · L100-L115 — async def test_pool_limits_use_config(self, monkeypatch)
- TestSemaphoreManager · class · L118-L176 — class TestSemaphoreManager
- test_default_semaphore_value · method · L121-L129 — def test_default_semaphore_value(self, monkeypatch)
- test_acquire_and_release · method · L132-L140 — async def test_acquire_and_release(self)
- test_semaphore_limits_concurrency · method · L143-L176 — async def test_semaphore_limits_concurrency(self, monkeypatch)
