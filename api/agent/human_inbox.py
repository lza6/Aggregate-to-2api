"""api/agent/human_inbox.py — v12.0.1 T3 human_input 审批真通道。

DAG human_input 节点的进程内审批收件箱（替代占位串）：
- create()：节点执行时创建审批请求（req_id/run_id/node_id/prompt），状态 pending
- decide()：审批端点写入 approve/reject（幂等：仅 pending 可决策）
- wait()：节点执行侧轮询等待决策或超时（interval 0.5s）

设计：进程内 dict + threading.Lock（与 dag 内存 store 同级生命周期；SQLite 持久化
留 v12.0.2，run 本身已有 dag_runs.db 重建能力）。零外部依赖，付费红线无关。
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

_TERMINAL = {"approved", "rejected"}


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
    """审批收件箱（进程内单例）。"""

    def __init__(self) -> None:
        self._requests: dict[str, InboxRequest] = {}
        self._lock = threading.Lock()

    def create(self, run_id: str, node_id: str, prompt: str) -> InboxRequest:
        req = InboxRequest(req_id=uuid.uuid4().hex[:16], run_id=run_id, node_id=node_id, prompt=prompt[:2000])
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
            return req  # type: ignore[return-value]

    def reset(self) -> None:
        """测试钩子：清空全部请求（conftest 每用例隔离）。"""
        with self._lock:
            self._requests.clear()

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


# 模块级单例（进程内；测试用 reset() 隔离）
human_inbox = HumanInbox()

__all__ = ["HumanInbox", "InboxRequest", "human_inbox"]
