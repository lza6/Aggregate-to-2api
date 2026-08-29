# api/turnstile_client.py

- TurnstileError · class · L28-L29 — class TurnstileError(RuntimeError)
- TurnstileRateLimited · class · L32-L34 — class TurnstileRateLimited(TurnstileError)
- _SolverRejected · class · L37-L39 — class _SolverRejected(TurnstileError)
- _get_client · function · L46-L63 — def _get_client() -> httpx.AsyncClient
- close_client · function · L66-L71 — async def close_client() -> None
- solve_turnstile · function · L74-L176 — async def solve_turnstile( cf_solver_url: str | None = None, url: str = "", sitekey: str = "", timeout: float = 90.0, proxy: str | None = None, ) -> tuple[str, float]
- _solve_turnstile · function · L179-L243 — async def _solve_turnstile( cf_solver_url: str, url: str, sitekey: str, timeout: float, proxy: str | None, ) -> str
