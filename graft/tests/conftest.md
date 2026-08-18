# tests/conftest.py

- tmp_db · function · L20-L34 — def tmp_db()
- no_proxy_env · function · L38-L44 — def no_proxy_env()
- mock_env · function · L48-L70 — def mock_env()
- port_open · function · L73-L78 — def port_open(port: int, host: str = "127.0.0.1") -> bool
- wait_port · function · L81-L87 — def wait_port(port: int, timeout: float, desc: str) -> bool
- mock_cfsolver · function · L91-L108 — def mock_cfsolver()
- app_with_mocks · function · L112-L168 — async def app_with_mocks(mock_cfsolver, tmp_db, no_proxy_env)
