"""号池（账号池）包（P0-1 拆分；P0-F2 进一步按 mixin 拆分）。

子模块：
- _constants: 常量 + `_pkg_attr()` 运行时包属性读取工具
- _base: AccountPoolBase（连接生命周期 + MAB 评分 + async 兼容包装）
- borrow: BorrowMixin（FSM 借还/封号/冷却/自愈/租约/余额预测/lease）
- store: StoreMixin（CRUD：add/list/list_page/get/update_credits/consume_credits/mark）
- signin: SigninMixin（签到画像 + 每日签到巡检循环）
- stats: StatsMixin（看板/成本/补满速率画像）
- engine: EngineMixin（自动补号/延寿唤醒巡检循环）
- fsm: AccountStatus 枚举 + canonical()
- scoring: AdaptiveAccountScore MAB 评分器
- pool: AccountPool 多继承组合 + 单例 account_pool + 兼容 re-export

向后兼容：本包顶层 re-export 全部公共符号，
`from api.account_pool import AccountStatus` / `import api.account_pool as ap; ap.account_pool`
等旧 import 路径零改动可用。

被 monkeypatch 的常量（TARGET_NANOBANANA/REGISTER_COOLDOWN/SELFHEAL_MAX_RETRY/
MOCK_REGISTER）经 `_pkg_attr()` 运行时读包命名空间，patch 仍命中（见 .wolf/cerebrum.md
Do-Not-Repeat 2026-09-05）。
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
