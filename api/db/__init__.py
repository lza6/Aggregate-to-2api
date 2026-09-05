"""DB 包。由原单体 api/db.py 拆分而来。

- core.py: DB 类（连接管理/读写分离/批量写/查询/清理/幂等/DLQ/缓存持久化）
- migrations.py: schema 初始化 + 增量迁移 DDL（init_schema），core._init_schema 委托之
- queries.py: QueueDB（已废弃）+ task_to_public 函数
- queue_store.py: QueueStore（持久化队列异步实现，任务实际使用）

`from api.db import DB, task_to_public, QueueStore` 可导入新实现；
`QueueDB` 为兼容已废弃的同步旧实现。
"""

from __future__ import annotations

from .core import DB
from .migrations import init_schema
from .queries import QueueDB, task_to_public
from .queue_store import QueueStore

__all__ = ["DB", "QueueDB", "QueueStore", "init_schema", "task_to_public"]
