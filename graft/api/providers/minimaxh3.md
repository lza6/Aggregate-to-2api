# api/providers/minimaxh3.py

- Minimaxh3Provider · class · L49-L276 — class Minimaxh3Provider(Provider)
- __init__ · method · L55-L60 — def __init__(self) -> None
- _build_models · method · L62-L72 — def _build_models(self) -> None
- startup · method · L75-L84 — async def startup(self) -> None
- _load_accounts · method · L86-L92 — def _load_accounts(self) -> list[dict]
- shutdown · method · L94-L97 — async def shutdown(self) -> None
- needs_account · method · L99-L100 — def needs_account(self) -> bool
- _next_account · method · L103-L114 — def _next_account(self) -> dict
- credits · method · L116-L117 — async def credits(self) -> int | None
- _load_accounts_total · method · L119-L121 — def _load_accounts_total(self) -> int
- refresh_credits · method · L123-L140 — async def refresh_credits(self) -> None
- generate · method · L143-L196 — async def generate(self, model: str, prompt: str, aspect_ratio: str, images: list[bytes] | None = None, resolution: str = "1K", download: bool = False, **kw) -> GenerationResult
- _submit_image · method · L198-L213 — async def _submit_image(self, cookie, upstream, prompt, aspect_ratio, resolution, images)
- _submit_video · method · L215-L227 — async def _submit_video(self, cookie, upstream, prompt, aspect_ratio, resolution, duration)
- _handle_submit · method · L229-L247 — async def _handle_submit(self, r: httpx.Response, cookie) -> str
- _find_by_cookie · method · L249-L253 — def _find_by_cookie(self, cookie) -> dict | None
- _poll · method · L255-L276 — async def _poll(self, cookie, generation_id, resource, timeout) -> str
