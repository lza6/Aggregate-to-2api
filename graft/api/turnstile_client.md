# api/turnstile_client.py

- TurnstileError · class · L28-L29 — class TurnstileError(RuntimeError)
- _SolverRejected · class · L32-L33 — class _SolverRejected(TurnstileError)
- _get_client · function · L40-L53 — def _get_client() -> httpx.AsyncClient
- close_client · function · L56-L61 — async def close_client() -> None
- solve_turnstile · function · L64-L112 — async def solve_turnstile( cf_solver_url: str, url: str, sitekey: str, timeout: float, proxy: str | None = None, ) -> tuple[str, float]
- _solve_turnstile · function · L115-L162 — async def _solve_turnstile( cf_solver_url: str, url: str, sitekey: str, timeout: float, proxy: str | None, ) -> str
