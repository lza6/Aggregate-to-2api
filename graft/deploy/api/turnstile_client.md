# deploy/api/turnstile_client.py

- TurnstileError · class · L27-L28 — class TurnstileError(RuntimeError)
- _SolverRejected · class · L31-L32 — class _SolverRejected(TurnstileError)
- _get_client · function · L39-L52 — def _get_client() -> httpx.AsyncClient
- close_client · function · L55-L60 — async def close_client() -> None
- solve_turnstile · function · L63-L100 — async def solve_turnstile( cf_solver_url: str, url: str, sitekey: str, timeout: float, proxy: str | None = None, ) -> tuple[str, float]
- _solve_turnstile · function · L103-L150 — async def _solve_turnstile( cf_solver_url: str, url: str, sitekey: str, timeout: float, proxy: str | None, ) -> str
