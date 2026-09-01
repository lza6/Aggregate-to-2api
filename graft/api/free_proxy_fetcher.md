# api/free_proxy_fetcher.py

- _is_valid_public_ip · function · L133-L149 — def _is_valid_public_ip(host: str) -> bool
- parse_ipport_text · function · L152-L180 — def parse_ipport_text(text: str) -> list[str]
- parse_geonode_json · function · L183-L208 — def parse_geonode_json(text: str) -> list[str]
- parse_source · function · L211-L216 — def parse_source(payload: str, fmt: str) -> list[str]
- _precheck · function · L219-L231 — async def _precheck(url: str) -> bool
- FreeProxyFetcher · class · L234-L316 — class FreeProxyFetcher
- __init__ · method · L237-L241 — def __init__(self, pool) -> None
- start · method · L243-L250 — async def start(self) -> None
- stop · method · L252-L261 — async def stop(self) -> None
- _loop · method · L263-L277 — async def _loop(self) -> None
- _fetch_once · method · L279-L316 — async def _fetch_once(self) -> dict
- _check · function · L305-L307 — async def _check(u: str) -> bool
