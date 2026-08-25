"""DB 包。由原单体 api/db.py 拆分而来。

- core.py: DB 类完整实现（连接管理/读写分离/批量写/查询/清理/幂等/DLQ/缓存持久化）
- queries.py: QueueDB 类 + task_to_public 函数

`from api.db import DB, task_to_public, QueueDB` 完全向后兼容。
"""
from __future__ import annotations

from .core import DB
from .queries import QueueDB, task_to_public
from .queue_store import QueueStore

__all__ = ["DB", "QueueDB", "QueueStore", "task_to_public"]