# api/providers/aifreeforever.py

- AifreeforeverProvider · class · L69-L225 — class AifreeforeverProvider(Provider)
- __init__ · method · L75-L78 — def __init__(self) -> None
- _build_models · method · L80-L93 — def _build_models(self) -> None
- needs_proxy_per_request · method · L95-L96 — def needs_proxy_per_request(self) -> bool
- generate · method · L98-L173 — async def generate( self, model: str, prompt: str, aspect_ratio: str, images: list[bytes] | None = None, resolution: str = "1K", download: bool = False, **kw, ) -> GenerationResult: # 1) 分配出口 IP（优先代理池轮换，无代理时回退直连）
- _headers · method · L176-L188 — def _headers(self, token: str | None = None) -> dict
- _moderate · method · L190-L197 — async def _moderate(self, image_bytes: bytes, proxy: str | None) -> bool
- _generate · method · L199-L219 — async def _generate(self, token, upstream, prompt, aspect_ratio, images, proxy) -> list[str]
- _download · method · L221-L225 — async def _download(self, url, proxy) -> bytes
