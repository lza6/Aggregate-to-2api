"""CAPTCHA/CF 求解结果统一协议包（v15-B）。

将两条求解通道（turnstile / cf_clearance）的结果统一为 CaptchaResult，
供上层以同构方式消费。纯增量：既有返回结构（tuple / dict）保持不变。
"""

from .protocol import (
    CF_CLEARANCE_SOLVER,
    TURNSTILE_SOLVER,
    CaptchaResult,
    from_cf_clearance,
    from_turnstile,
)

__all__ = [
    "CF_CLEARANCE_SOLVER",
    "TURNSTILE_SOLVER",
    "CaptchaResult",
    "from_cf_clearance",
    "from_turnstile",
]
