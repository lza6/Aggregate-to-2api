"""号池常量 + 运行时包属性读取工具（P0-F2 拆分叶子模块）。

常量原定义在 pool.py，拆分后移到此叶子模块。pool.py 与各 mixin 子模块
（borrow/signin/stats/store/_base）均从此处 import 常量；但**被 monkeypatch
的常量**（TARGET_NANOBANANA / REGISTER_COOLDOWN / SELFHEAL_MAX_RETRY /
MOCK_REGISTER）在运行时必须经 `_pkg_attr()` 读取包命名空间，否则 from-import
值拷贝不命中 patch（见 .wolf/cerebrum.md Do-Not-Repeat 2026-09-05）。

向后兼容：`from api.account_pool.pool import TARGET_NANOBANANA` 等旧路径经
pool.py 的 re-export 仍可用；`from api.account_pool import TARGET_NANOBANANA`
经 __init__.py 的 re-export 仍可用。
"""

from __future__ import annotations

import logging
import os
import sys

from ..providers.base import MOCK_REGISTER  # noqa: F401  (re-export 源)

log = logging.getLogger("account_pool")

DB_FILE = os.getenv("IF_ACCOUNT_DB_FILE", "data/account_pool.db")
# nanobanana 目标常驻账号数（默认 10000）
TARGET_NANOBANANA = int(os.getenv("IF_NANOBANANA_ACCOUNT_TARGET", "10000"))
# 补号冷却（秒）：注册器连续失败时退避，防风控。
# 7x24h 不间断注册：每成功 1 个后休息 90s（24h ≈ 960 个），
# 既绕开 temp-mail / cf_solver 的 429 限流，又持续累积号池。
REGISTER_COOLDOWN = int(os.getenv("IF_REGISTER_COOLDOWN", "90"))
# 默认账号冷却期（秒）：cooling 状态满此时长后可自动唤醒尝试签到/恢复
DEFAULT_COOLING_PERIOD_SECONDS = float(os.getenv("IF_ACCOUNT_COOLING_PERIOD", "72000"))  # 20 hours
# 借号租约超时（秒）：超过此时长自动重置为 active 防死锁
BORROW_LEASE_TIMEOUT_SECONDS = float(os.getenv("IF_ACCOUNT_BORROW_TIMEOUT", "300"))
# P1-7 自愈：cooling 账号签到恢复连续失败超此次数才转 dead（此前唤醒即尝试、一次失败即恢复原状等下轮）
SELFHEAL_MAX_RETRY = int(os.getenv("IF_ACCOUNT_SELFHEAL_MAX_RETRY", "3"))
# P1-7 自愈退避：第 n 次失败后下次唤醒冷却 = cooling_timeout * SELFHEAL_BACKOFF_BASE ** n（封顶）
SELFHEAL_BACKOFF_BASE = 2.0
SELFHEAL_BACKOFF_CAP = 7 * 86400.0  # 退避封顶 7 天


def _pkg_attr(name: str, default):
    """运行时读取包命名空间 `api.account_pool.<name>`。

    拆分前这些常量是 `api/account_pool.py` 的模块全局，测试用
    `monkeypatch.setattr("api.account_pool.TARGET_NANOBANANA", ...)` 直接改那份绑定。
    拆分后定义物理位于本模块（_constants.py），`__init__.py` 与 `pool.py` 的 re-export
    是值拷贝——若子模块读自身全局或 from-import，patch 包命名空间不会命中（原版天然命中）。
    此处运行时解析包属性，保持旧契约。
    """
    mod = sys.modules.get(__package__) or sys.modules.get("api.account_pool")
    return getattr(mod, name, default) if mod is not None else default
