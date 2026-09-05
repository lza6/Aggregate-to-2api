"""号池（账号池）包（P0-1 拆分）。

子模块：
- fsm: AccountStatus 枚举 + canonical()
- scoring: AdaptiveAccountScore MAB 评分器
- pool: AccountPool 管理器 + 单例 account_pool + 常量

向后兼容：本包顶层 re-export 全部公共符号，
`from api.account_pool import AccountStatus` / `import api.account_pool as ap; ap.account_pool`
等旧 import 路径零改动可用。
"""

from __future__ import annotations

from .fsm import AccountStatus
from .pool import (
    BORROW_LEASE_TIMEOUT_SECONDS,
    DB_FILE,
    DEFAULT_COOLING_PERIOD_SECONDS,
    MOCK_REGISTER,
    REGISTER_COOLDOWN,
    SELFHEAL_BACKOFF_BASE,
    SELFHEAL_BACKOFF_CAP,
    SELFHEAL_MAX_RETRY,
    TARGET_NANOBANANA,
    AccountPool,
    account_pool,
)
from .scoring import AdaptiveAccountScore

__all__ = [
    "AccountPool",
    "AccountStatus",
    "AdaptiveAccountScore",
    "BORROW_LEASE_TIMEOUT_SECONDS",
    "DB_FILE",
    "DEFAULT_COOLING_PERIOD_SECONDS",
    "MOCK_REGISTER",
    "REGISTER_COOLDOWN",
    "SELFHEAL_BACKOFF_BASE",
    "SELFHEAL_BACKOFF_CAP",
    "SELFHEAL_MAX_RETRY",
    "TARGET_NANOBANANA",
    "account_pool",
]
