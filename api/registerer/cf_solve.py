"""cf_solver 调用封装：Turnstile token 求解（P0-5 从 registerer.py 拆出）。

向后兼容：`api.registerer` 旧路径仍 re-export 全部符号。
当前实现复用全局 `turnstile_client` + `solver_guard`，本模块仅做 import re-export，
避免与 registerer/flow.py 形成循环依赖。
"""

from __future__ import annotations

from .. import turnstile_client
from ..solver_guard import solver_guard

__all__ = ["solver_guard", "turnstile_client"]
