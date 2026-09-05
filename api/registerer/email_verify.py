"""邮箱验证码/链接提取与等待封装（P0-5 从 registerer.py 拆出）。

向后兼容：`api.registerer` 旧路径仍 re-export 全部符号。

注：实际的 `_extract_code` / `_extract_verify_link` 正则快路径定义在 `utils.py`，
本模块仅 re-export，避免重复实现导致行为分叉。
"""

from __future__ import annotations

from ..email_pool import email_pool
from .utils import _extract_code, _extract_verify_link

__all__ = ["_extract_code", "_extract_verify_link", "email_pool"]
