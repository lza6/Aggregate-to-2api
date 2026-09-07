"""DAG run 内存存储（进程内，重启即清；v9.0.0-A）。

单机内存态足够（与现有 agent memory 同模式）；v9.0.0-B 可扩展 SQLite 持久化。
"""

from __future__ import annotations

from typing import Any


class _DagRunStore:
    """进程内 run 存储：upsert/get/list（线程安全由 asyncio 单事件循环保证）。"""

    def __init__(self) -> None:
        self._runs: dict[str, Any] = {}

    def upsert(self, run: Any) -> None:
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> Any | None:
        return self._runs.get(run_id)

    def list(self, limit: int = 20) -> list[Any]:
        # 按创建时间倒序（内存 dict 插入序即创建序，反转取最近）
        return [r for r in reversed(list(self._runs.values()))][:limit]

    def clear(self) -> None:
        self._runs.clear()


# 模块级单例（全服务共享；测试可用独立实例）
dag_run_store = _DagRunStore()


__all__ = ["_DagRunStore", "dag_run_store"]
