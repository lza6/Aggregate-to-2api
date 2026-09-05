# tests/test_http_pool_config.py

- TestHttpPoolConfig · class · L22-L56 — class TestHttpPoolConfig
- test_defaults_are_correct · method · L25-L39 — def test_defaults_are_correct(self)
- test_env_overrides · method · L41-L56 — def test_env_overrides(self, monkeypatch)
- TestTurnstileClientPoolConfig · class · L59-L93 — class TestTurnstileClientPoolConfig
- _get_pool · method · L63-L73 — def _get_pool(client)
- test_pool_limits_use_config · method · L76-L93 — async def test_pool_limits_use_config(self, monkeypatch)
- TestImagefreeClientPoolConfig · class · L96-L128 — class TestImagefreeClientPoolConfig
- _get_pool · method · L100-L110 — def _get_pool(client)
- test_pool_limits_use_config · method · L113-L128 — async def test_pool_limits_use_config(self, monkeypatch)
- TestSemaphoreManager · class · L131-L191 — class TestSemaphoreManager
- test_default_semaphore_value · method · L134-L143 — def test_default_semaphore_value(self, monkeypatch)
- test_acquire_and_release · method · L146-L154 — async def test_acquire_and_release(self)
- test_semaphore_limits_concurrency · method · L157-L191 — async def test_semaphore_limits_concurrency(self, monkeypatch)
