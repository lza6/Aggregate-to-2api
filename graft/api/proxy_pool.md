# api/proxy_pool.py

- _cooldown_for · function · L38-L42 — def _cooldown_for(use_count: int) -> int
- _safe_url · function · L45-L52 — def _safe_url(url: str) -> str
- ProxyEntry · class · L55-L120 — class ProxyEntry
- __init__ · method · L72-L86 — def __init__(self, url: str, source: str = "residential") -> None
- cooling · method · L89-L91 — def cooling(self) -> bool
- available · method · L93-L108 — def available(self, now: float) -> bool: # 冷却中不可用
- snapshot · method · L110-L120 — def snapshot(self) -> dict
- ProxyPool · class · L123-L332 — class ProxyPool
- __init__ · method · L124-L129 — def __init__(self, proxy_file: str = "") -> None
- load_file · method · L131-L146 — def load_file(self, path: str) -> int
- add_free · method · L148-L159 — def add_free(self, urls: list[str]) -> int
- reap_free · method · L161-L173 — def reap_free(self) -> int
- enabled · method · L176-L177 — def enabled(self) -> bool
- acquire · method · L179-L215 — async def acquire(self, force_rotate: bool = True, prefer_source: str | None = None) -> str | None
- mark_failure · method · L217-L231 — async def mark_failure(self, url: str, rate_limited: bool = True) -> None
- mark_success · method · L233-L238 — async def mark_success(self, url: str) -> None
- apply_trace_result · method · L240-L262 — async def apply_trace_result(self, url: str, geo: dict) -> None
- snapshot · method · L264-L332 — def snapshot(self, page: int = 1, page_size: int = 20) -> dict
