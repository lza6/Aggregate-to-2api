"""DAG run 内存存储（进程内，重启即清；v9.0.0-A 原实现，v10.0.0 接口对齐 sqlite）。

v10.0.0：双实现契约统一——upsert/get/list(limit,status)/cleanup/close。
内存实现为进程内态（缺省/降级）；sqlite 持久化见 agent_dag_store_sqlite.py。
"""

from __future__ import annotations

import time
from typing import Any


class _DagRunStore:
    """进程内 run 存储（线程安全由 asyncio 单事件循环保证）。"""

    def __init__(self) -> None:
        self._runs: dict[str, Any] = {}

    def upsert(self, run: Any) -> None:
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> Any | None:
        return self._runs.get(run_id)

    def list(self, limit: int = 20, status: str | None = None) -> list[Any]:
        """按创建时间倒序（最近在前）；可选 status 过滤（v10.0.0 接口对齐 sqlite）。"""
        runs = list(self._runs.values())
        runs.sort(key=lambda r: getattr(r, "created_at", 0) or 0, reverse=True)
        if status:
            runs = [r for r in runs if getattr(r, "status", None) == status]
        return runs[:limit]

    def cleanup(self, retention_days: float = 7, now: float | None = None) -> int:
        """删除早于 now-retention_days 的 run，返回删除数（v10.0.0 接口对齐 sqlite）。"""
        now = now if now is not None else time.time()
        cutoff = now - retention_days * 86400
        expired = [k for k, v in self._runs.items() if (getattr(v, "created_at", 0) or 0) < cutoff]
        for k in expired:
            self._runs.pop(k, None)
        return len(expired)

    def clear(self) -> None:
        self._runs.clear()

    async def close(self) -> None:
        """接口对齐 sqlite store（内存实现无连接，no-op）。"""
        self._runs.clear()


# 模块级单例（全服务共享；测试可用独立实例）
dag_run_store = _DagRunStore()


__all__ = ["_DagRunStore", "dag_run_store"]
