# api/free_proxy_fetcher.py

- _is_valid_public_ip · function · L89-L99 — def _is_valid_public_ip(host: str) -> bool
- parse_ipport_text · function · L102-L122 — def parse_ipport_text(text: str) -> list[str]
- parse_geonode_json · function · L125-L150 — def parse_geonode_json(text: str) -> list[str]
- parse_source · function · L153-L158 — def parse_source(payload: str, fmt: str) -> list[str]
- _precheck · function · L161-L174 — async def _precheck(url: str) -> bool
- FreeProxyFetcher · class · L177-L256 — class FreeProxyFetcher
- __init__ · method · L180-L184 — def __init__(self, pool) -> None
- start · method · L186-L193 — async def start(self) -> None
- stop · method · L195-L204 — async def stop(self) -> None
- _loop · method · L206-L216 — async def _loop(self) -> None
- _fetch_once · method · L218-L256 — async def _fetch_once(self) -> dict
- _check · function · L244-L246 — async def _check(u: str) -> bool
