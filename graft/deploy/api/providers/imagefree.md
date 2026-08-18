# deploy/api/providers/imagefree.py

- ImagefreeProvider · class · L21-L76 — class ImagefreeProvider(Provider)
- __init__ · method · L27-L31 — def __init__(self) -> None
- _build_models · method · L33-L46 — def _build_models(self) -> None
- needs_proxy_per_request · method · L48-L49 — def needs_proxy_per_request(self) -> bool
- credits · method · L51-L52 — async def credits(self) -> int | None
- generate · method · L54-L76 — async def generate(self, model: str, prompt: str, aspect_ratio: str, images: list[bytes] | None = None, resolution: str = "1K", download: bool = False, **kw) -> GenerationResult
