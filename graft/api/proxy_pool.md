# api/proxy_pool.py

- _cooldown_for · function · L40-L44 — def _cooldown_for(use_count: int) -> int
- _safe_url · function · L47-L54 — def _safe_url(url: str) -> str
- ProxyEntry · class · L57-L104 — class ProxyEntry
- __init__ · method · L61-L70 — def __init__(self, url: str, source: str = "residential") -> None
- cooling · method · L73-L75 — def cooling(self) -> bool
- available · method · L77-L92 — def available(self, now: float) -> bool: # 冷却中不可用
- snapshot · method · L94-L104 — def snapshot(self) -> dict
- ProxyPool · class · L107-L233 — class ProxyPool
- __init__ · method · L108-L113 — def __init__(self, proxy_file: str = "") -> None
- load_file · method · L115-L130 — def load_file(self, path: str) -> int
- add_free · method · L132-L143 — def add_free(self, urls: list[str]) -> int
- reap_free · method · L145-L157 — def reap_free(self) -> int
- enabled · method · L160-L161 — def enabled(self) -> bool
- acquire · method · L163-L199 — async def acquire(self, force_rotate: bool = True, prefer_source: str | None = None) -> str | None
- mark_failure · method · L201-L215 — async def mark_failure(self, url: str, rate_limited: bool = True) -> None
- mark_success · method · L217-L222 — async def mark_success(self, url: str) -> None
- snapshot · method · L224-L233 — def snapshot(self) -> dict
