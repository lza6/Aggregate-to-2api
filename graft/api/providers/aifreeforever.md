# api/providers/aifreeforever.py

- AifreeforeverProvider · class · L68-L224 — class AifreeforeverProvider(Provider)
- __init__ · method · L74-L77 — def __init__(self) -> None
- _build_models · method · L79-L92 — def _build_models(self) -> None
- needs_proxy_per_request · method · L94-L95 — def needs_proxy_per_request(self) -> bool
- generate · method · L97-L172 — async def generate( self, model: str, prompt: str, aspect_ratio: str, images: list[bytes] | None = None, resolution: str = "1K", download: bool = False, **kw, ) -> GenerationResult: # 1) 分配出口 IP（优先代理池轮换，无代理时回退直连）
- _headers · method · L175-L187 — def _headers(self, token: str | None = None) -> dict
- _moderate · method · L189-L196 — async def _moderate(self, image_bytes: bytes, proxy: str | None) -> bool
- _generate · method · L198-L218 — async def _generate(self, token, upstream, prompt, aspect_ratio, images, proxy) -> list[str]
- _download · method · L220-L224 — async def _download(self, url, proxy) -> bytes
