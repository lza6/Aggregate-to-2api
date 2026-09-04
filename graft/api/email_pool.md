# api/email_pool.py

- EmailPool · class · L62-L380 — class EmailPool
- __init__ · method · L89-L112 — def __init__(self, db_path: str = DB_FILE, custom_sources: list[BaseMailSource] | None = None) -> None
- _ensure_conn · method · L114-L137 — async def _ensure_conn(self) -> aiosqlite.Connection
- _close_conn_safe · method · L139-L148 — async def _close_conn_safe(self) -> None
- _init_schema · method · L150-L170 — async def _init_schema(self, conn: aiosqlite.Connection) -> None
- _load_used · method · L172-L175 — async def _load_used(self, conn: aiosqlite.Connection) -> set[str]
- _find_source · method · L177-L182 — def _find_source(self, name: str) -> BaseMailSource | None
- risky_domains · method · L184-L193 — async def risky_domains(self, min_fails: int = 3) -> set[str]
- get_sources · method · L195-L197 — def get_sources(self) -> list[BaseMailSource]
- allocate · method · L200-L271 — async def allocate( self, provider: str, want_fresh: bool = True, prefer_source: str | None = None, prefer_domain: str | None = None, ) -> tuple[str, dict]
- wait_for_mail · method · L274-L305 — async def wait_for_mail( self, address: str, source_state: dict | None, timeout: float = 90.0, contains: str | None = None, ) -> dict | None
- record · method · L308-L337 — async def record(self, email: str, provider: str, status: str = "ok", note: str = "") -> None
- async_record · method · L339-L343 — async def async_record( self, email: str, provider: str, status: str = "ok", note: str = "" ) -> None
- registered_providers · method · L345-L350 — async def registered_providers(self, email: str) -> list[str]
- stats · method · L352-L380 — async def stats(self) -> dict
