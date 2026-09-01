# api/turnstile_client.py

- TurnstileError · class · L29-L30 — class TurnstileError(RuntimeError)
- TurnstileRateLimited · class · L33-L36 — class TurnstileRateLimited(TurnstileError)
- _SolverRejected · class · L39-L42 — class _SolverRejected(TurnstileError)
- _get_client · function · L49-L68 — def _get_client() -> httpx.AsyncClient
- close_client · function · L71-L76 — async def close_client() -> None
- solve_turnstile · function · L79-L181 — async def solve_turnstile( cf_solver_url: str | None = None, url: str = "", sitekey: str = "", timeout: float = 90.0, proxy: str | None = None, ) -> tuple[str, float]
- _solve_turnstile · function · L184-L248 — async def _solve_turnstile( cf_solver_url: str, url: str, sitekey: str, timeout: float, proxy: str | None, ) -> str
