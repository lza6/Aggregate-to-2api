# api/registerer.py

- _browser_headers · function · L25-L30 — def _browser_headers(origin: str, referer: str | None = None) -> dict
- _th · function · L33-L38 — async def _th(fn, *a, **k)
- Minimaxh3Registerer · class · L42-L139 — class Minimaxh3Registerer
- __init__ · method · L50-L54 — def __init__(self) -> None
- _ensure_client · method · L56-L69 — def _ensure_client(self, email: str = "") -> None
- register_one · method · L71-L136 — async def register_one(self) -> dict | None
- checkin · method · L138-L139 — async def checkin(self, acc: dict) -> int | None
- _extract_code · function · L142-L149 — def _extract_code(mail: dict | None) -> str | None
- NanobananaRegisterer · class · L153-L291 — class NanobananaRegisterer
- __init__ · method · L161-L165 — def __init__(self) -> None
- _ensure_client · method · L167-L177 — def _ensure_client(self, email: str = "") -> None
- register_one · method · L179-L231 — async def register_one(self) -> dict | None
- checkin · method · L233-L291 — async def checkin(self, acc: dict) -> int | None
- _extract_verify_link · function · L294-L301 — def _extract_verify_link(mail: dict | None) -> str | None
- build_registerers · function · L305-L309 — def build_registerers() -> dict[str, object]
