# deploy/api/providers/nanobanana.py

- NanobananaProvider · class · L49-L237 — class NanobananaProvider(Provider)
- __init__ · method · L55-L60 — def __init__(self) -> None
- _build_models · method · L62-L70 — def _build_models(self) -> None
- needs_account · method · L72-L73 — def needs_account(self) -> bool
- startup · method · L75-L79 — async def startup(self) -> None
- shutdown · method · L81-L84 — async def shutdown(self) -> None
- _load_accounts · method · L86-L92 — def _load_accounts(self) -> list[dict]
- _next_account · method · L94-L103 — def _next_account(self) -> dict
- credits · method · L105-L107 — async def credits(self) -> int | None
- _rsc_encode · method · L110-L113 — def _rsc_encode(self, obj: dict) -> str
- generate · method · L115-L145 — async def generate(self, model: str, prompt: str, aspect_ratio: str, images: list[bytes] | None = None, resolution: str = "1K", download: bool = False, **kw) -> GenerationResult
- _action_headers · method · L147-L153 — def _action_headers(self, cookie: str, action_id: str) -> dict
- _submit_image · method · L155-L162 — async def _submit_image(self, cookie, upstream, prompt, aspect_ratio, resolution) -> str
- _submit_edit · method · L164-L183 — async def _submit_edit(self, cookie, upstream, prompt, aspect_ratio, images) -> str
- _parse_action_response · method · L185-L214 — async def _parse_action_response(self, r: httpx.Response) -> str
- _poll_task · method · L216-L237 — async def _poll_task(self, cookie, task_id, timeout) -> str
