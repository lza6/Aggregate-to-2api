# api/providers/nanobanana.py

- NanobananaProvider · class · L51-L239 — class NanobananaProvider(Provider)
- __init__ · method · L57-L62 — def __init__(self) -> None
- _build_models · method · L64-L72 — def _build_models(self) -> None
- needs_account · method · L74-L75 — def needs_account(self) -> bool
- startup · method · L77-L81 — async def startup(self) -> None
- shutdown · method · L83-L86 — async def shutdown(self) -> None
- _load_accounts · method · L88-L94 — def _load_accounts(self) -> list[dict]
- _next_account · method · L96-L105 — def _next_account(self) -> dict
- credits · method · L107-L109 — async def credits(self) -> int | None
- _rsc_encode · method · L112-L115 — def _rsc_encode(self, obj: dict) -> str
- generate · method · L117-L147 — async def generate(self, model: str, prompt: str, aspect_ratio: str, images: list[bytes] | None = None, resolution: str = "1K", download: bool = False, **kw) -> GenerationResult
- _action_headers · method · L149-L155 — def _action_headers(self, cookie: str, action_id: str) -> dict
- _submit_image · method · L157-L164 — async def _submit_image(self, cookie, upstream, prompt, aspect_ratio, resolution) -> str
- _submit_edit · method · L166-L185 — async def _submit_edit(self, cookie, upstream, prompt, aspect_ratio, images) -> str
- _parse_action_response · method · L187-L216 — async def _parse_action_response(self, r: httpx.Response) -> str
- _poll_task · method · L218-L239 — async def _poll_task(self, cookie, task_id, timeout) -> str
