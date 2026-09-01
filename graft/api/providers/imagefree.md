# api/providers/imagefree.py

- ImagefreeProvider · class · L49-L189 — class ImagefreeProvider(Provider)
- __init__ · method · L55-L59 — def __init__(self) -> None
- _build_models · method · L61-L74 — def _build_models(self) -> None
- needs_proxy_per_request · method · L76-L77 — def needs_proxy_per_request(self) -> bool
- credits · method · L79-L80 — async def credits(self) -> int | None
- generate · method · L82-L189 — async def generate( self, model: str, prompt: str, aspect_ratio: str, images: list[bytes] | None = None, resolution: str = "1K", download: bool = False, **kw, ) -> GenerationResult
