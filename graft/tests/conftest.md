# tests/conftest.py

- tmp_db · function · L27-L46 — async def tmp_db()
- no_proxy_env · function · L50-L56 — def no_proxy_env()
- mock_env · function · L60-L82 — def mock_env()
- port_open · function · L85-L90 — def port_open(port: int, host: str = "127.0.0.1") -> bool
- wait_port · function · L93-L99 — def wait_port(port: int, timeout: float, desc: str) -> bool
- mock_cfsolver · function · L103-L122 — def mock_cfsolver()
- _app_instance · function · L126-L208 — async def _app_instance(mock_cfsolver)
- pytest_sessionfinish · function · L211-L218 — def pytest_sessionfinish(session, exitstatus)
- app_with_mocks · function · L222-L256 — async def app_with_mocks(_app_instance)
