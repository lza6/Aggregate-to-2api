"""号池管理器 AccountPool + 单例（P0-1 从 account_pool.py 拆出；P0-F2 进一步拆分）。

`AccountPool` 原为单一巨型类（1111 行），P0-F2 按职责拆为多继承组合：
- `_base.AccountPoolBase`：连接生命周期 + MAB 评分 + async 兼容包装
- `borrow.BorrowMixin`：FSM 借还/封号/冷却/自愈/租约/余额预测/lease
- `store.StoreMixin`：CRUD（add/list/list_page/get/update_credits/consume_credits/mark）
- `signin.SigninMixin`：签到画像 + 每日签到巡检循环
- `stats.StatsMixin`：看板/成本/补满速率画像
- `engine.EngineMixin`：自动补号/延寿唤醒巡检循环
- `_constants`：常量 + `_pkg_attr()` 工具

向后兼容（CRITICAL）：
- `api.account_pool.AccountPool` / `api.account_pool.account_pool` 旧 import 路径仍可用
- 全部公共符号（常量/类/方法签名/返回结构）保持不变
- 被 monkeypatch 的常量（TARGET_NANOBANANA/REGISTER_COOLDOWN/SELFHEAL_MAX_RETRY/
  MOCK_REGISTER）子模块经 `_pkg_attr()` 运行时读包命名空间，patch 仍命中
"""

from __future__ import annotations

from ._base import AccountPoolBase
from ._constants import (
    BORROW_LEASE_TIMEOUT_SECONDS,
    DB_FILE,
    DEFAULT_COOLING_PERIOD_SECONDS,
    MOCK_REGISTER,
    REGISTER_COOLDOWN,
    SELFHEAL_BACKOFF_BASE,
    SELFHEAL_BACKOFF_CAP,
    SELFHEAL_MAX_RETRY,
    TARGET_NANOBANANA,
    _pkg_attr,
)
from .borrow import BorrowMixin
from .engine import EngineMixin
from .signin import SigninMixin
from .stats import StatsMixin
from .store import StoreMixin

__all__ = [
    "AccountPool",
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
    # 工具函数也 re-export（测试/脚本可能用）
    "_pkg_attr",
]


class AccountPool(
    BorrowMixin,
    SigninMixin,
    StatsMixin,
    StoreMixin,
    EngineMixin,
    AccountPoolBase,
):
    """号池管理器：多继承组合各 mixin。

    方法解析顺序（MRO）：BorrowMixin → SigninMixin → StatsMixin →
    StoreMixin → EngineMixin → AccountPoolBase → object。
    所有 mixin 依赖 AccountPoolBase 的 _ensure_conn/_lock/_selfheal_retry/
    registerers 等基础设施；__init__ 由 AccountPoolBase 提供。
    """


# 模块级单例
account_pool = AccountPool()
