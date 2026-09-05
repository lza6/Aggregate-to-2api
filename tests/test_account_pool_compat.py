"""account_pool 拆分兼容契约（P0-1）。

拆分 `api/account_pool.py` → `api/account_pool/` 包后，以下三种 import 路径必须全部可用，
单例一致，枚举字面量不变，canonical 行为不变。任何一条失败即视为拆分破坏了公共接口。
"""

from __future__ import annotations

import api.account_pool as legacy
from api.account_pool import (
    BORROW_LEASE_TIMEOUT_SECONDS,
    DB_FILE,
    DEFAULT_COOLING_PERIOD_SECONDS,
    REGISTER_COOLDOWN,
    TARGET_NANOBANANA,
    AccountPool,
    AccountStatus,
    AdaptiveAccountScore,
    account_pool,
)


def test_module_path_singleton_consistency() -> None:
    """`api.account_pool.account_pool` 单例与包 re-export 的 `account_pool` 是同一对象。"""
    assert legacy.account_pool is account_pool
    assert isinstance(account_pool, AccountPool)


def test_import_account_pool_as_namespace() -> None:
    """`import api.account_pool as ap; ap.account_pool` 旧路径可用。"""
    assert hasattr(legacy, "account_pool")
    assert hasattr(legacy, "AccountStatus")
    assert hasattr(legacy, "AccountPool")
    assert hasattr(legacy, "AdaptiveAccountScore")
    assert legacy.account_pool is account_pool


def test_constants_reexported() -> None:
    """常量全部可从包顶层 import。"""
    assert isinstance(DB_FILE, str)
    assert isinstance(TARGET_NANOBANANA, int)
    assert isinstance(REGISTER_COOLDOWN, int)
    assert isinstance(DEFAULT_COOLING_PERIOD_SECONDS, float)
    assert isinstance(BORROW_LEASE_TIMEOUT_SECONDS, float)
    # 与 module 命名空间一致
    assert legacy.DB_FILE == DB_FILE
    assert legacy.TARGET_NANOBANANA == TARGET_NANOBANANA


def test_account_status_enum_literal_unchanged() -> None:
    """枚举字符串字面量不得变化（已入库，改了破坏存量数据）。"""
    assert AccountStatus.UNREGISTERED.value == "unregistered"
    assert AccountStatus.REGISTERING.value == "registering"
    assert AccountStatus.ACTIVE.value == "active"
    assert AccountStatus.OK.value == "ok"
    assert AccountStatus.WORKING.value == "working"
    assert AccountStatus.COOLING.value == "cooling"
    assert AccountStatus.EXHAUSTED.value == "exhausted"
    assert AccountStatus.DEAD.value == "dead"
    assert AccountStatus.BANNED.value == "banned"


def test_canonical_mapping() -> None:
    """canonical 标准化行为不变。"""
    assert AccountStatus.canonical("ok") == "active"
    assert AccountStatus.canonical("active") == "active"
    assert AccountStatus.canonical("exhausted") == "cooling"
    assert AccountStatus.canonical("cooling") == "cooling"
    assert AccountStatus.canonical("banned") == "dead"
    assert AccountStatus.canonical("dead") == "dead"
    assert AccountStatus.canonical("working") == "working"
    assert AccountStatus.canonical("registering") == "registering"
    assert AccountStatus.canonical("unregistered") == "unregistered"
    # 空串回退 active；未知非空串原样透传（原实现 line 81 `return s or "active"`）
    assert AccountStatus.canonical("") == "active"
    assert AccountStatus.canonical("unknown") == "unknown"


def test_adaptive_score_constructible() -> None:
    """AdaptiveAccountScore 独立类可实例化且 score 方法可用。"""
    s = AdaptiveAccountScore("test@example.com")
    assert s.email == "test@example.com"
    assert s.success_count == 0
    assert s.fail_count == 0
    # 更新一次成功，score 应为有限数
    s.update_result(500.0, True)
    assert s.success_count == 1
    assert isinstance(s.score(), float)


def test_account_pool_methods_intact() -> None:
    """关键公共方法签名仍存在（只校验存在性，不调用 DB）。"""
    for name in (
        "borrow_account",
        "release_account",
        "mark_dead",
        "mark_cooling",
        "wake_cooling_accounts",
        "lease",
        "add",
        "list",
        "list_page",
        "get",
        "update_credits",
        "consume_credits",
        "mark",
        "set_checkin",
        "set_checkin_profile",
        "counts",
        "total_credits",
        "cost_summary",
        "growth_stats",
        "start",
        "stop",
        "dashboard",
        "report_result",
        # async 兼容别名
        "async_get",
        "async_borrow_account",
        "async_release_account",
        "async_mark_dead",
        "async_consume_credits",
        "async_get_adaptive",
    ):
        assert hasattr(AccountPool, name), f"AccountPool.{name} 丢失（拆分破坏公共接口）"
