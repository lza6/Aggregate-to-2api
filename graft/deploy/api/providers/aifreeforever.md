# deploy/api/providers/aifreeforever.py

- AifreeforeverProvider · class · L63-L203 — class AifreeforeverProvider(Provider)
- __init__ · method · L69-L72 — def __init__(self) -> None
- _build_models · method · L74-L82 — def _build_models(self) -> None
- needs_proxy_per_request · method · L84-L85 — def needs_proxy_per_request(self) -> bool
- generate · method · L87-L154 — async def generate(self, model: str, prompt: str, aspect_ratio: str, images: list[bytes] | None = None, resolution: str = "1K", download: bool = False, **kw) -> GenerationResult: # 1) 分配出口 IP（优先代理池轮换，无代理时回退直连）
- _headers · method · L157-L166 — def _headers(self, token: str | None = None) -> dict
- _moderate · method · L168-L173 — async def _moderate(self, image_bytes: bytes, proxy: str | None) -> bool
- _generate · method · L175-L197 — async def _generate(self, token, upstream, prompt, aspect_ratio, images, proxy) -> list[str]
- _download · method · L199-L203 — async def _download(self, url, proxy) -> bytes
