# tests/test_http_pool_config.py

- TestHttpPoolConfig · class · L22-L55 — class TestHttpPoolConfig
- test_defaults_are_correct · method · L25-L39 — def test_defaults_are_correct(self)
- test_env_overrides · method · L41-L55 — def test_env_overrides(self, monkeypatch)
- TestTurnstileClientPoolConfig · class · L58-L92 — class TestTurnstileClientPoolConfig
- _get_pool · method · L62-L72 — def _get_pool(client)
- test_pool_limits_use_config · method · L75-L92 — async def test_pool_limits_use_config(self, monkeypatch)
- TestImagefreeClientPoolConfig · class · L95-L127 — class TestImagefreeClientPoolConfig
- _get_pool · method · L99-L109 — def _get_pool(client)
- test_pool_limits_use_config · method · L112-L127 — async def test_pool_limits_use_config(self, monkeypatch)
- TestSemaphoreManager · class · L130-L189 — class TestSemaphoreManager
- test_default_semaphore_value · method · L133-L141 — def test_default_semaphore_value(self, monkeypatch)
- test_acquire_and_release · method · L144-L152 — async def test_acquire_and_release(self)
- test_semaphore_limits_concurrency · method · L155-L189 — async def test_semaphore_limits_concurrency(self, monkeypatch)
