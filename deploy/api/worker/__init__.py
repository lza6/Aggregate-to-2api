"""Worker 包。由原单体 api/worker.py 拆分而来。

- engine.py: Engine 类 + _WorkerHandle + 辅助函数
- token_pool.py: _TokenPool / TokenPoolManager

`from api.worker import Engine, QueueFull, CountedPriorityQueue, TokenPoolManager, _TokenPool`
完全向后兼容。
"""
from __future__ import annotations

from .engine import (
    CountedPriorityQueue,
    Engine,
    QueueFull,
    _is_token_rejected,
    _safe_proxy_label,
)
from .token_pool import _TokenPool, TokenPoolManager

__all__ = [
    "Engine",
    "QueueFull",
    "CountedPriorityQueue",
    "TokenPoolManager",
    "_TokenPool",
    "_safe_proxy_label",
    "_is_token_rejected",
]