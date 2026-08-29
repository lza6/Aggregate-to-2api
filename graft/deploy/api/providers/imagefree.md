# deploy/api/providers/imagefree.py

- ImagefreeProvider · class · L23-L134 — class ImagefreeProvider(Provider)
- __init__ · method · L29-L33 — def __init__(self) -> None
- _build_models · method · L35-L48 — def _build_models(self) -> None
- needs_proxy_per_request · method · L50-L51 — def needs_proxy_per_request(self) -> bool
- credits · method · L53-L54 — async def credits(self) -> int | None
- generate · method · L56-L134 — async def generate(self, model: str, prompt: str, aspect_ratio: str, images: list[bytes] | None = None, resolution: str = "1K", download: bool = False, **kw) -> GenerationResult
