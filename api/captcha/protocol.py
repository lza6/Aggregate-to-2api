"""统一 CAPTCHA/CF 求解结果协议（v15-B）。

背景：项目存在两条求解通道，返回结构不统一：
- ``api.turnstile_client.solve_turnstile()`` → ``tuple[str, float]``（token, 秒）
- ``api.cf_clearance_solver.CfClearanceSolver.solve()`` → ``dict | None``

``CaptchaResult`` 作为统一载体（frozen 不可变），两通道各自提供工厂映射：
- ``from_turnstile``：turnstile 通道（token + 求解毫秒）
- ``from_cf_clearance``：cf_clearance 通道 dict → 结果；None → ok=False 空结果

纯增量协议：不改变任何既有返回结构，仅提供统一消费入口。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 求解通道标识（写入 CaptchaResult.solver，便于调用方区分来源）
TURNSTILE_SOLVER = "turnstile"
CF_CLEARANCE_SOLVER = "cf_clearance"


@dataclass(frozen=True)
class CaptchaResult:
    """统一 CAPTCHA/CF 求解结果。

    - token：有效求解凭证（turnstile token / cf_clearance cookie 值）
    - cookies：cf_clearance 通道返回的完整 cookie 列表（turnstile 通道为空）
    - user_agent：求解所用 UA（cf_clearance 绑定 IP+UA，回放须一致）
    - elapsed_ms：求解耗时（毫秒，两通道统一口径）
    - solver：来源通道（TURNSTILE_SOLVER / CF_CLEARANCE_SOLVER）
    """

    token: str = ""
    cookies: list[dict] = field(default_factory=list)
    user_agent: str = ""
    elapsed_ms: float = 0.0
    solver: str = ""

    @property
    def ok(self) -> bool:
        """是否拿到有效 token（token 非空）。"""
        return bool(self.token)


def from_turnstile(token: str, elapsed_ms: float = 0.0) -> CaptchaResult:
    """turnstile 通道 → CaptchaResult。

    Args:
        token: turnstile 求解 token
        elapsed_ms: 求解耗时（毫秒；turnstile 原生秒数由调用方转换后传入）
    """
    return CaptchaResult(token=token, elapsed_ms=elapsed_ms, solver=TURNSTILE_SOLVER)


def from_cf_clearance(d: dict[str, Any] | None) -> CaptchaResult:
    """cf_clearance 通道 dict → CaptchaResult。

    Args:
        d: ``CfClearanceSolver.solve()`` 的返回 dict；None（或空 dict）表示
           纯协议失败 / 无挑战，返回 ok=False 的空 CaptchaResult。
    """
    if not d:
        return CaptchaResult(solver=CF_CLEARANCE_SOLVER)
    return CaptchaResult(
        token=str(d.get("cf_clearance", "") or ""),
        cookies=list(d.get("cookies", []) or []),
        user_agent=str(d.get("user_agent", "") or ""),
        elapsed_ms=float(d.get("elapsed_ms", 0.0) or 0.0),
        solver=CF_CLEARANCE_SOLVER,
    )
