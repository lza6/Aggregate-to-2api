# deploy/api/cache.py

- LRUCache · class · L11-L126 — class LRUCache
- __init__ · method · L19-L24 — def __init__(self, maxsize: int = 128, ttl: float = 5.0) -> None
- maxsize · method · L27-L28 — def maxsize(self) -> int
- ttl · method · L31-L32 — def ttl(self) -> float
- get · method · L36-L48 — async def get(self, key: str) -> Any | None
- set · method · L50-L59 — async def set(self, key: str, value: Any) -> None
- invalidate · method · L61-L64 — async def invalidate(self, key: str) -> None
- clear · method · L66-L69 — async def clear(self) -> None
- start_reaper · method · L73-L77 — def start_reaper(self) -> None
- stop_reaper · method · L79-L89 — async def stop_reaper(self) -> None
- _reaper_loop · method · L91-L100 — async def _reaper_loop(self) -> None
- _purge_expired · method · L102-L110 — async def _purge_expired(self) -> None
- size · method · L115-L117 — def size(self) -> int
- snapshot · method · L119-L126 — async def snapshot(self) -> dict
