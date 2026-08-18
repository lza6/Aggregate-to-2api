# deploy/api/registerer.py

- _browser_headers · function · L26-L31 — def _browser_headers(origin: str, referer: str | None = None) -> dict
- _th · function · L34-L39 — async def _th(fn, *a, **k)
- Minimaxh3Registerer · class · L43-L140 — class Minimaxh3Registerer
- __init__ · method · L51-L55 — def __init__(self) -> None
- _ensure_client · method · L57-L70 — def _ensure_client(self, email: str = "") -> None
- register_one · method · L72-L137 — async def register_one(self) -> dict | None
- checkin · method · L139-L140 — async def checkin(self, acc: dict) -> int | None
- _extract_code · function · L143-L150 — def _extract_code(mail: dict | None) -> str | None
- NanobananaRegisterer · class · L154-L292 — class NanobananaRegisterer
- __init__ · method · L162-L166 — def __init__(self) -> None
- _ensure_client · method · L168-L178 — def _ensure_client(self, email: str = "") -> None
- register_one · method · L180-L232 — async def register_one(self) -> dict | None
- checkin · method · L234-L292 — async def checkin(self, acc: dict) -> int | None
- _extract_verify_link · function · L295-L302 — def _extract_verify_link(mail: dict | None) -> str | None
- build_registerers · function · L306-L310 — def build_registerers() -> dict[str, object]
