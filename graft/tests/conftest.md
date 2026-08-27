# tests/conftest.py

- tmp_db · function · L26-L45 — async def tmp_db()
- no_proxy_env · function · L49-L55 — def no_proxy_env()
- mock_env · function · L59-L81 — def mock_env()
- port_open · function · L84-L89 — def port_open(port: int, host: str = "127.0.0.1") -> bool
- wait_port · function · L92-L98 — def wait_port(port: int, timeout: float, desc: str) -> bool
- mock_cfsolver · function · L102-L119 — def mock_cfsolver()
- _app_instance · function · L123-L199 — async def _app_instance(mock_cfsolver)
- pytest_sessionfinish · function · L202-L208 — def pytest_sessionfinish(session, exitstatus)
- app_with_mocks · function · L212-L246 — async def app_with_mocks(_app_instance)
