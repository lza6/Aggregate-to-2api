"""号池 FSM：账号生命周期状态枚举（P0-1 从 account_pool.py 拆出）。

枚举字符串字面量已入库（data/account_pool.db），不得变更；canonical() 行为不变。
向后兼容：`api.account_pool.AccountStatus` 旧 import 路径仍可用（见包 __init__）。
"""

from __future__ import annotations

import enum


class AccountStatus(str, enum.Enum):
    """标准账号生命周期状态枚举。"""

    UNREGISTERED = "unregistered"  # 未注册
    REGISTERING = "registering"  # 注册中
    ACTIVE = "active"  # 就绪可用 (同义词 'ok')
    OK = "ok"  # 兼容历史状态
    WORKING = "working"  # 工作负载中 (被借出)
    COOLING = "cooling"  # 冷却/额度耗尽中 (同义词 'exhausted')
    EXHAUSTED = "exhausted"  # 兼容历史状态
    DEAD = "dead"  # 封号/失效 (同义词 'banned')
    BANNED = "banned"  # 兼容历史状态

    @classmethod
    def canonical(cls, status: str) -> str:
        """标准化状态名称（保持内部一致，向外兼容）。"""
        s = (status or "").strip().lower()
        if s in ("ok", "active"):
            return "active"
        if s in ("exhausted", "cooling"):
            return "cooling"
        if s in ("banned", "dead"):
            return "dead"
        if s == "registering":
            return "registering"
        if s == "working":
            return "working"
        if s == "unregistered":
            return "unregistered"
        return s or "active"
