# deploy/api/free_proxy_fetcher.py

- _is_valid_public_ip · function · L90-L100 — def _is_valid_public_ip(host: str) -> bool
- parse_ipport_text · function · L103-L123 — def parse_ipport_text(text: str) -> list[str]
- parse_geonode_json · function · L126-L151 — def parse_geonode_json(text: str) -> list[str]
- parse_source · function · L154-L159 — def parse_source(payload: str, fmt: str) -> list[str]
- _precheck · function · L162-L175 — async def _precheck(url: str) -> bool
- FreeProxyFetcher · class · L178-L257 — class FreeProxyFetcher
- __init__ · method · L181-L185 — def __init__(self, pool) -> None
- start · method · L187-L194 — async def start(self) -> None
- stop · method · L196-L205 — async def stop(self) -> None
- _loop · method · L207-L217 — async def _loop(self) -> None
- _fetch_once · method · L219-L257 — async def _fetch_once(self) -> dict
- _check · function · L245-L247 — async def _check(u: str) -> bool
