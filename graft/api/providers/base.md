# api/providers/base.py

- ModelSpec · class · L36-L48 — class ModelSpec
- GenerationResult · class · L52-L59 — class GenerationResult
- ProviderError · class · L62-L63 — class ProviderError(RuntimeError)
- ProviderRateLimited · class · L66-L67 — class ProviderRateLimited(ProviderError)
- Provider · class · L70-L147 — class Provider(abc.ABC)
- __init__ · method · L77-L87 — def __init__(self, config: dict | None = None) -> None
- startup · method · L90-L91 — async def startup(self) -> None
- shutdown · method · L93-L94 — async def shutdown(self) -> None
- supports · method · L97-L98 — def supports(self, capability: str) -> bool
- generate · method · L102-L106 — async def generate(self, model: str, prompt: str, aspect_ratio: str, images: list[bytes] | None = None, resolution: str = "1K", download: bool = False, **kw) -> GenerationResult
- credits · method · L109-L111 — async def credits(self) -> int | None
- health · method · L113-L115 — async def health(self) -> dict
- health_check · method · L118-L120 — async def health_check(self) -> str
- mark_down · method · L122-L129 — def mark_down(self, reason: str) -> None
- mark_up · method · L131-L138 — def mark_up(self) -> None
- needs_proxy_per_request · method · L141-L143 — def needs_proxy_per_request(self) -> bool
- needs_account · method · L145-L147 — def needs_account(self) -> bool
