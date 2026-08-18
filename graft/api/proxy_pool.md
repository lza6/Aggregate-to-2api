# api/proxy_pool.py

- _cooldown_for · function · L39-L43 — def _cooldown_for(use_count: int) -> int
- _safe_url · function · L46-L53 — def _safe_url(url: str) -> str
- ProxyEntry · class · L56-L103 — class ProxyEntry
- __init__ · method · L60-L69 — def __init__(self, url: str, source: str = "residential") -> None
- cooling · method · L72-L74 — def cooling(self) -> bool
- available · method · L76-L91 — def available(self, now: float) -> bool: # 冷却中不可用
- snapshot · method · L93-L103 — def snapshot(self) -> dict
- ProxyPool · class · L106-L228 — class ProxyPool
- __init__ · method · L107-L111 — def __init__(self, proxy_file: str = "") -> None
- load_file · method · L113-L128 — def load_file(self, path: str) -> int
- add_free · method · L130-L141 — def add_free(self, urls: list[str]) -> int
- reap_free · method · L143-L155 — def reap_free(self) -> int
- enabled · method · L158-L159 — def enabled(self) -> bool
- acquire · method · L161-L196 — def acquire(self, force_rotate: bool = True, prefer_source: str | None = None) -> str | None
- mark_failure · method · L198-L211 — def mark_failure(self, url: str, rate_limited: bool = True) -> None
- mark_success · method · L213-L217 — def mark_success(self, url: str) -> None
- snapshot · method · L219-L228 — def snapshot(self) -> dict
