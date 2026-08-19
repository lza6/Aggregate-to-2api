# tests/conftest.py

- event_loop · function · L20-L29 — def event_loop()
- tmp_db · function · L33-L47 — def tmp_db()
- no_proxy_env · function · L51-L57 — def no_proxy_env()
- mock_env · function · L61-L83 — def mock_env()
- port_open · function · L86-L91 — def port_open(port: int, host: str = "127.0.0.1") -> bool
- wait_port · function · L94-L100 — def wait_port(port: int, timeout: float, desc: str) -> bool
- mock_cfsolver · function · L104-L121 — def mock_cfsolver()
- _app_instance · function · L125-L185 — async def _app_instance(mock_cfsolver, event_loop)
- app_with_mocks · function · L189-L207 — async def app_with_mocks(_app_instance)
