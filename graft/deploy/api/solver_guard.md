# deploy/api/solver_guard.py

- SolverGuard · class · L26-L131 — class SolverGuard
- __init__ · method · L27-L33 — def __init__(self, circuit_threshold: int = 5, probe_interval: float = 30.0, window_seconds: float = 300.0, window_maxlen: int = 10000) -> None
- _reset · method · L35-L47 — def _reset(self) -> None
- record_success · method · L50-L59 — def record_success(self, duration_sec: float) -> None
- record_failure · method · L61-L74 — def record_failure(self, reason: str, duration_sec: float | None = None) -> None
- record_rejected · method · L76-L78 — def record_rejected(self) -> None
- allow_solve · method · L81-L90 — def allow_solve(self) -> bool
- circuit_open · method · L93-L94 — def circuit_open(self) -> bool
- consecutive_failures · method · L97-L98 — def consecutive_failures(self) -> int
- snapshot · method · L101-L126 — def snapshot(self) -> dict
- _trim_window · method · L128-L131 — def _trim_window(self) -> None
