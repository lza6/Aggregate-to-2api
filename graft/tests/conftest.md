# tests/conftest.py

- tmp_db · function · L27-L46 — async def tmp_db()
- _reset_settings_singleton · function · L50-L62 — def _reset_settings_singleton()
- no_proxy_env · function · L66-L72 — def no_proxy_env()
- mock_env · function · L76-L98 — def mock_env()
- port_open · function · L101-L106 — def port_open(port: int, host: str = "127.0.0.1") -> bool
- wait_port · function · L109-L115 — def wait_port(port: int, timeout: float, desc: str) -> bool
- mock_cfsolver · function · L119-L138 — def mock_cfsolver()
- _app_instance · function · L142-L233 — async def _app_instance(mock_cfsolver)
- pytest_sessionfinish · function · L236-L270 — def pytest_sessionfinish(session, exitstatus)
- _close_all · function · L246-L254 — async def _close_all()
- app_with_mocks · function · L274-L308 — async def app_with_mocks(_app_instance)
