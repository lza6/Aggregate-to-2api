# api/account_pool.py

- AccountPool · class · L38-L260 — class AccountPool
- __init__ · method · L39-L48 — def __init__(self, db_path: str = DB_FILE) -> None
- _init_schema · method · L50-L68 — def _init_schema(self) -> None
- add · method · L71-L82 — def add(self, provider: str, email: str, cookie: str, password: str | None = None, credits: int = 0, status: str = "ok", note: str = "") -> None
- list · method · L84-L94 — def list(self, provider: str | None = None, status: str | None = None) -> list[dict]
- get · method · L96-L98 — def get(self, provider: str) -> list[dict]
- update_credits · method · L100-L104 — def update_credits(self, provider: str, email: str, credits: int) -> None
- mark · method · L106-L110 — def mark(self, provider: str, email: str, status: str, note: str = "") -> None
- set_checkin · method · L112-L116 — def set_checkin(self, provider: str, email: str, checkin_at: float) -> None
- counts · method · L118-L124 — def counts(self) -> dict
- total_credits · method · L126-L129 — def total_credits(self, provider: str) -> int
- start · method · L132-L140 — async def start(self) -> None: # 补号循环按配置开关；minimaxh3 若 turnstile 被站点拒（外部求解兼容）可经 IF_MINIMAXH3_AUTOREG=0 关闭， # 避免无谓消耗 cf_solver 单槽（主站 token 预取优先）。nanobanana 每日签到续额。
- _autoreg_enabled · method · L143-L146 — def _autoreg_enabled(provider: str) -> bool
- stop · method · L148-L153 — async def stop(self) -> None
- _autoregister_loop · method · L155-L219 — async def _autoregister_loop(self, provider: str) -> None
- _daily_checkin_loop · method · L221-L243 — async def _daily_checkin_loop(self, provider: str) -> None
- dashboard · method · L245-L260 — def dashboard(self) -> dict
