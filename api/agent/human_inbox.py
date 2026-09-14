"""api/agent/human_inbox.py — v12.0.1 T3 human_input 审批真通道。

DAG human_input 节点的审批收件箱（替代占位串，v12.x P0-1 起 SQLite 持久化）：
- create()：节点执行时创建审批请求（req_id/run_id/node_id/prompt），状态 pending
- decide()：审批端点写入 approve/reject（幂等：仅 pending 可决策）
- wait()：节点执行侧轮询等待决策或超时（interval 0.5s）

持久化设计（v12.x P0-1，仿 api/agent/memory.py MemoryStore 模式）：
- 同步 sqlite3 + threading.Lock，db_path 可注入（默认 data/human_inbox.db）
- 内存缓存（dict）为热路径（get/list 不触盘），写操作先落库再更新缓存：
  崩溃/重启后重启即从 SQLite 重建（重启实例同 db_path → 历史审批可查）
- 表 inbox_requests(req_id PK, run_id, node_id, prompt, status, note,
  created_at, decided_at)；status: pending / approved / rejected / timeout
- 禁止 __init__ 里 asyncio.run（Do-Not-Repeat#3）；建表在 __init__ 同步跑
  （sqlite3.connect 线程安全，无需事件循环）

依赖：仅标准库（sqlite3/threading）。付费红线无关。
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

_DEFAULT_DB = "data/human_inbox.db"
_TERMINAL = {"approved", "rejected"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS inbox_requests (
    req_id      TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL,
    node_id     TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    note        TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    decided_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_inbox_run ON inbox_requests(run_id);
CREATE INDEX IF NOT EXISTS idx_inbox_status ON inbox_requests(status);
"""


@dataclass
class InboxRequest:
    """单条审批请求（节点执行侧创建，审批侧决策）。"""

    req_id: str
    run_id: str
    node_id: str
    prompt: str
    status: str = "pending"  # pending / approved / rejected / timeout
    note: str = ""
    created_at: float = field(default_factory=time.time)
    decided_at: float | None = None


class HumanInbox:
    """审批收件箱（SQLite 持久化 + 内存热缓存）。"""

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        self.db_path = db_path
        self._requests: dict[str, InboxRequest] = {}
        self._lock = threading.RLock()
        self._init_schema()
        self._load_from_db()

    def _conn(self) -> sqlite3.Connection:
        """同步连接：isolation_level=None + WAL + busy_timeout（对齐主流程 Do-Not-Repeat#1）。

        默认 fallback journal + 隐式事务会让跨 store 写锁窗口拉长（全量并发撞锁
        database is locked）；isolation_level=None（autocommit）+ WAL 与
        api/db/core.py/ip_blocklist_store.py 一致，写者互斥窗口最短。
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL").fetchone()  # 消费结果防 "statements in progress"
        return conn

    def _init_schema(self) -> None:
        """建表（CREATE IF NOT EXISTS，向后兼容不改旧表）。"""
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def _load_from_db(self) -> None:
        """启动时从 SQLite 重建内存缓存（重启后历史审批可查）。"""
        try:
            with self._conn() as conn:
                rows = conn.execute("SELECT * FROM inbox_requests").fetchall()
            loaded: dict[str, InboxRequest] = {}
            for r in rows:
                loaded[r["req_id"]] = InboxRequest(
                    req_id=r["req_id"],
                    run_id=r["run_id"],
                    node_id=r["node_id"],
                    prompt=r["prompt"],
                    status=r["status"],
                    note=r["note"],
                    created_at=r["created_at"],
                    decided_at=r["decided_at"],
                )
            with self._lock:
                self._requests = loaded
        except sqlite3.Error:  # DBLOCK / I/O 异常降级：进程内可用，不崩应用
            self._requests = {}

    def _save(self, req: InboxRequest) -> None:
        """单条落库（UPSERT）。"""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO inbox_requests(req_id, run_id, node_id, prompt, status, note, created_at, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(req_id) DO UPDATE SET
                    status=excluded.status, note=excluded.note, decided_at=excluded.decided_at
                """,
                (req.req_id, req.run_id, req.node_id, req.prompt, req.status, req.note, req.created_at, req.decided_at),
            )
            conn.commit()

    def create(self, run_id: str, node_id: str, prompt: str) -> InboxRequest:
        req = InboxRequest(req_id=uuid.uuid4().hex[:16], run_id=run_id, node_id=node_id, prompt=prompt[:2000])
        self._save(req)
        with self._lock:
            self._requests[req.req_id] = req
        return req

    def decide(self, req_id: str, decision: str, note: str = "") -> InboxRequest | None:
        """决策（幂等：仅 pending 可决策，重复决策返回原状态不覆盖）。"""
        if decision not in ("approve", "reject"):
            raise ValueError(f"非法决策：{decision}（仅 approve/reject）")
        with self._lock:
            req = self._requests.get(req_id)
            if req is None:
                return None
            if req.status in _TERMINAL:
                return req
            req.status = "approved" if decision == "approve" else "rejected"
            req.note = note[:500]
            req.decided_at = time.time()
        self._save(req)
        return req

    def get(self, req_id: str) -> InboxRequest | None:
        with self._lock:
            return self._requests.get(req_id)

    def list(self, run_id: str | None = None, status: str | None = None) -> list[InboxRequest]:
        with self._lock:
            reqs = list(self._requests.values())
        if run_id:
            reqs = [r for r in reqs if r.run_id == run_id]
        if status:
            reqs = [r for r in reqs if r.status == status]
        return sorted(reqs, key=lambda r: r.created_at, reverse=True)

    async def wait(self, req_id: str, timeout: float, interval: float = 0.5) -> InboxRequest:
        """执行侧等待决策：决策到达/超时即返回（超时 status=timeout 并落库）。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            req = self.get(req_id)
            if req is not None and req.status in _TERMINAL:
                return req
            await asyncio.sleep(interval)
        with self._lock:
            req = self._requests.get(req_id)
            if req is not None and req.status not in _TERMINAL:
                req.status = "timeout"
                req.decided_at = time.time()
                self._save(req)
            return req  # type: ignore[return-value]

    def reset(self) -> None:
        """测试钩子：清空内存 + 清空表（conftest 每用例隔离）。"""
        with self._lock:
            self._requests.clear()
        try:
            with self._conn() as conn:
                conn.execute("DELETE FROM inbox_requests")
                conn.commit()
        except sqlite3.Error:
            pass

    def public_state(self, req: InboxRequest) -> dict[str, Any]:
        return {
            "req_id": req.req_id,
            "run_id": req.run_id,
            "node_id": req.node_id,
            "prompt": req.prompt,
            "status": req.status,
            "note": req.note,
            "created_at": req.created_at,
            "decided_at": req.decided_at,
        }


# ── 模块单例 + 工厂（仿 config 工厂：测试可用 reset_human_inbox 隔离）──
_human_inbox: HumanInbox | None = None


def _resolve_db_path() -> str:
    """解析审批库路径：优先环境变量 IF_HUMAN_INBOX_DB，缺省 data/human_inbox.db。

    延迟到首次调用（而非 import 期）读取，确保测试 monkeypatch env 后生效。
    """
    import os

    return os.getenv("IF_HUMAN_INBOX_DB", "").strip() or _DEFAULT_DB


def get_human_inbox(db_path: str | None = None) -> HumanInbox:
    """获取全局 HumanInbox 单例（db_path 首次调用时固化；测试可用 reset 重建）。"""
    global _human_inbox
    if _human_inbox is None:
        _human_inbox = HumanInbox(db_path or _resolve_db_path())
    return _human_inbox


def reset_human_inbox(db_path: str | None = None) -> HumanInbox:
    """重置全局 HumanInbox（测试钩子）：丢弃旧实例并重建。"""
    global _human_inbox
    _human_inbox = HumanInbox(db_path or _resolve_db_path())
    return _human_inbox


# 模块级单例（向后兼容 `from api.agent.human_inbox import human_inbox`）
human_inbox = get_human_inbox()

__all__ = ["HumanInbox", "InboxRequest", "human_inbox", "get_human_inbox", "reset_human_inbox"]
