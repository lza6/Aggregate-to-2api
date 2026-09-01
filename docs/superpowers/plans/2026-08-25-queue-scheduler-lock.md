# 队列调度、并发控制与图生图分布式锁 — 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将内存队列升级为三层有界优先级队列 + 瞬时落盘 + SSE 广播增强，并将图生图 PID 文件锁演进为 SQLite 行级原子租约锁（Lease Lock）。

**架构：** 队列保持现有 `CountedPriorityQueue`（0/1/2 优先级），`submit_priority()` 入队时同步写 SQLite WAL（`task_queue` 表），进程重启可从持久化队列恢复。图生图互斥锁升级为 `edit_leases` 表（`key PRIMARY KEY`），通过 `INSERT OR REPLACE WHERE expires_at < now` 原子获取，持锁期间后台心跳续租，超时自动被他人抢占。

**技术栈：** Python 3.10+ / asyncio / SQLite (aiosqlite) / pytest / FastAPI

**规格：** `docs/superpowers/specs/2026-08-25-queue-scheduler-lock-design.md`

---

## 文件结构

### 修改文件
| 文件 | 职责 |
|------|------|
| `api/config/__init__.py` | 新增 `IF_EDIT_LEASE_ENABLED`、`IF_EDIT_LEASE_TTL` 配置 |
| `api/db/__init__.py` | `QueueDB` 增加 WAL 落盘/恢复；新增 `LeaseStore` |
| `api/worker/engine.py` | `submit_priority()` 入队时同步落盘；启动时恢复 |
| `api/dispatch_edit.py` | 互斥锁改为可切换实现（文件锁 / SQLite 租约锁） |
| `deploy/api/db.py` | 同步 db 模块变更（deploy copy） |

### 创建文件
| 文件 | 职责 |
|------|------|
| `api/db/queue_store.py` | 持久化队列存储（`task_queue` 表） |
| `api/db/lease_store.py` | SQLite 租约锁存储（`edit_leases` 表） |
| `tests/test_edit_lease.py` | Lease Lock 单元测试 |
| `tests/test_queue_store.py` | 持久化队列落盘/恢复测试 |
| `scripts/e2e_lease_lock.py` | 图生图租约锁 E2E 验证脚本 |

---

## 任务 1：新增租约锁配置项

**文件：**
- 修改：`api/config/__init__.py`（Settings 类 + 模块级常量）
- 修改：`api/config/edit.py`（EditSettings 子类）

- [ ] **步骤 1：修改 `api/config/edit.py` 增加配置字段**

在 `EditSettings` 中添加：

```python
edit_lease_enabled: bool = Field(
    False, validation_alias="IF_EDIT_LEASE_ENABLED"
)
edit_lease_ttl: int = Field(
    30, validation_alias="IF_EDIT_LEASE_TTL"
)
```

- [ ] **步骤 2：修改 `api/config/__init__.py` Settings 类**

在 `edit_mutex_enabled` 附近添加：

```python
edit_lease_enabled: bool = Field(
    False, validation_alias="IF_EDIT_LEASE_ENABLED"
)
edit_lease_ttl: int = Field(
    30, validation_alias="IF_EDIT_LEASE_TTL"
)
```

将 `_edit` 分组配置传入新增字段：

```python
self._edit = EditSettings(
    ...
    edit_lease_enabled=self.edit_lease_enabled,
    edit_lease_ttl=self.edit_lease_ttl,
)
```

- [ ] **步骤 3：加 Bool 清洗校验器**

将 `edit_lease_enabled` 加入 `_bool_str_coerce` 的 validator 列表。

- [ ] **步骤 4：加模块级常量**

```python
EDIT_LEASE_ENABLED = settings.edit_lease_enabled
EDIT_LEASE_TTL = settings.edit_lease_ttl
```

并添加进 `__all__` 列表。

- [ ] **步骤 5：运行配置测试验证**

运行：`pytest tests/test_config_validate.py -v`
预期：PASS

- [ ] **步骤 6：Commit**

```bash
git add api/config/__init__.py api/config/edit.py
git commit -m "feat(config): 新增图生图临时租约锁配置项 IF_EDIT_LEASE_*"
```

---

## 任务 2：持久化队列存储（QueueStore）

**文件：**
- 创建：`api/db/queue_store.py`

- [ ] **步骤 1：编写失败的测试**

创建 `tests/test_queue_store.py`：

```python
"""持久化队列存储单元测试。"""
import asyncio
import os
import tempfile

import pytest

from api.db.queue_store import QueueStore


@pytest.fixture
def store():
    path = tempfile.mktemp(suffix=".db")
    s = QueueStore(path)
    yield s
    asyncio.get_event_loop().run_until_complete(s.close())


class TestQueueStore:
    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, store):
        await store.enqueue("task-1", 2, 1)
        await store.enqueue("task-0", 0, 2)
        pending = await store.list_pending()
        assert sorted([(p, s, t) for p, s, t in pending]) == [
            (0, 2, "task-0"),
            (2, 1, "task-1"),
        ]

    @pytest.mark.asyncio
    async def test_mark_completed(self, store):
        await store.enqueue("task-1", 2, 1)
        await store.mark_completed("task-1")
        assert await store.list_pending() == []

    @pytest.mark.asyncio
    async def test_survives_reopen(self, store):
        path = store.path
        await store.enqueue("task-x", 0, 1)
        await store.close()
        store2 = QueueStore(path)
        pending = await store2.list_pending()
        assert pending == [(0, 1, "task-x")]
        await store2.close()
```

- [ ] **步骤 2：运行测试确认失败**

运行：`pytest tests/test_queue_store.py -v`
预期：FAIL（ModuleNotFoundError: api.db.queue_store）

- [ ] **步骤 3：实现 QueueStore**

```python
"""持久化任务队列存储（WAL 模式，_task_queue 表）。

设计在 api/db/__init__.py 的 QueueDB 之上或替代之，独立于 imagefree.db。
"""
from __future__ import annotations

import logging
import os
import time

import aiosqlite

log = logging.getLogger("db.queue_store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_queue (
    task_id TEXT PRIMARY KEY,
    priority INTEGER NOT NULL DEFAULT 2,
    seq INTEGER NOT NULL,
    created_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS idx_task_queue_status ON task_queue(status);
CREATE INDEX IF NOT EXISTS idx_task_queue_order ON task_queue(priority, seq);
"""


class QueueStore:
    """基于 SQLite WAL 的持久化任务队列。"""

    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def open(self) -> None:
        if self._conn is not None:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def enqueue(self, task_id: str, priority: int, seq: int) -> None:
        await self.open()
        await self._conn.execute(
            "INSERT OR REPLACE INTO task_queue(task_id, priority, seq, created_at, status)"
            " VALUES(?, ?, ?, ?, 'pending')",
            (task_id, priority, seq, time.time()),
        )
        await self._conn.commit()

    async def mark_processing(self, task_id: str) -> None:
        await self.open()
        await self._conn.execute(
            "UPDATE task_queue SET status='processing' WHERE task_id=?", (task_id,))
        await self._conn.commit()

    async def mark_completed(self, task_id: str) -> None:
        await self.open()
        await self._conn.execute("DELETE FROM task_queue WHERE task_id=?", (task_id,))
        await self._conn.commit()

    async def list_pending(self) -> list[tuple[int, int, str]]:
        """返回按 priority/seq 排序的 pending 任务 [(priority, seq, task_id)]。"""
        await self.open()
        cur = await self._conn.execute(
            "SELECT priority, seq, task_id FROM task_queue WHERE status != 'completed'"
            " ORDER BY priority ASC, seq ASC")
        rows = await cur.fetchall()
        return [(r["priority"], r["seq"], r["task_id"]) for r in rows]
```

- [ ] **步骤 4：运行测试确认通过**

运行：`pytest tests/test_queue_store.py -v`
预期：PASS（3 passed）

- [ ] **步骤 5：Commit**

```bash
git add api/db/queue_store.py tests/test_queue_store.py
git commit -m "feat(db): 新增持久化任务队列 QueueStore(WAL) + 测试"
```

---

## 任务 3：租约锁存储（LeaseStore）

**文件：**
- 创建：`api/db/lease_store.py`

- [ ] **步骤 1：编写失败的测试**

创建 `tests/test_edit_lease.py`：

```python
"""SQLite 租约锁（Lease Lock）单元测试。"""
import asyncio
import os
import tempfile
import time

import pytest

from api.db.lease_store import LeaseStore


@pytest.fixture
def store():
    path = tempfile.mktemp(suffix=".db")
    s = LeaseStore(path)
    yield s
    asyncio.get_event_loop().run_until_complete(s.close())


class TestLeaseStore:
    @pytest.mark.asyncio
    async def test_acquire_exclusive(self, store):
        ok1 = await store.acquire("key-a", "holder-1", "tok-1", ttl=30)
        assert ok1 is True
        ok2 = await store.acquire("key-a", "holder-2", "tok-2", ttl=30)
        assert ok2 is False  # 被占用

    @pytest.mark.asyncio
    async def test_expired_lock_taken_over(self, store):
        await store.acquire("key-b", "holder-1", "tok-1", ttl=-1)  # 立即过期
        ok2 = await store.acquire("key-b", "holder-2", "tok-2", ttl=30)
        assert ok2 is True

    @pytest.mark.asyncio
    async def test_release_by_token(self, store):
        await store.acquire("key-c", "holder-1", "tok-1", ttl=30)
        released = await store.release("key-c", "tok-1")
        assert released is True
        ok2 = await store.acquire("key-c", "holder-2", "tok-2", ttl=30)
        assert ok2 is True

    @pytest.mark.asyncio
    async def test_wrong_token_cannot_release(self, store):
        await store.acquire("key-d", "holder-1", "tok-1", ttl=30)
        released = await store.release("key-d", "wrong-token")
        assert released is False
        ok2 = await store.acquire("key-d", "holder-2", "tok-2", ttl=30)
        assert ok2 is False  # 仍被占

    @pytest.mark.asyncio
    async def test_renew_extends_expiry(self, store):
        await store.acquire("key-e", "holder-1", "tok-1", ttl=30)
        renewed = await store.renew("key-e", "tok-1", new_ttl=30)
        assert renewed is True
        row = await store.get("key-e")
        assert row["holder"] == "holder-1"
```

- [ ] **步骤 2：运行测试确认失败**

运行：`pytest tests/test_edit_lease.py -v`
预期：FAIL（ModuleNotFoundError: api.db.lease_store）

- [ ] **步骤 3：实现 LeaseStore**

```python
"""SQLite 行级原子租约锁存储（替代文件系统 PID 锁）。

设计：edit_leases 表，key 为 PRIMARY KEY。
- acquire：单条 SQL 内原子完成「检查过期 + 覆盖写入」，SQLite 写事务串行保证排他。
- renew：持锁者按 token 续租（延长 expires_at）。
- release：持锁者按 token 释放（DELETE WHERE key=? AND token=?）。
- 异常宕机：无续租 → expires_at 过期 → 新 acquire 自动覆盖，杜绝僵尸死锁。
"""
from __future__ import annotations

import logging
import os
import time

import aiosqlite

log = logging.getLogger("db.lease_store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS edit_leases (
    key TEXT PRIMARY KEY,
    holder TEXT NOT NULL,
    token TEXT NOT NULL,
    expires_at REAL NOT NULL,
    created_at REAL NOT NULL
);
"""


class LeaseStore:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def open(self) -> None:
        if self._conn is not None:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def acquire(self, key: str, holder: str, token: str, ttl: float) -> bool:
        """原子获取锁。当前无有效锁（expires_at 已过期或不存在）才成功。"""
        await self.open()
        now = time.time()
        async with self._conn.execute("BEGIN IMMEDIATE"):
            cur = await self._conn.execute(
                "SELECT expires_at FROM edit_leases WHERE key=?", (key,))
            row = await cur.fetchone()
            if row and row["expires_at"] > now:
                return False
            await self._conn.execute(
                "INSERT OR REPLACE INTO edit_leases(key, holder, token, expires_at, created_at)"
                " VALUES(?, ?, ?, ?, ?)",
                (key, holder, token, now + ttl, now),
            )
            await self._conn.commit()
            return True

    async def renew(self, key: str, token: str, new_ttl: float) -> bool:
        """持锁者续租。仅当 token 匹配时延长 expires_at。"""
        await self.open()
        now = time.time()
        cur = await self._conn.execute(
            "UPDATE edit_leases SET expires_at=? WHERE key=? AND token=?",
            (now + new_ttl, key, token),
        )
        await self._conn.commit()
        return cur.rowcount > 0

    async def release(self, key: str, token: str) -> bool:
        """按 token 释放。防止误删他人新锁。"""
        await self.open()
        cur = await self._conn.execute(
            "DELETE FROM edit_leases WHERE key=? AND token=?", (key, token))
        await self._conn.commit()
        return cur.rowcount > 0

    async def get(self, key: str) -> dict | None:
        await self.open()
        cur = await self._conn.execute(
            "SELECT key, holder, token, expires_at, created_at FROM edit_leases WHERE key=?",
            (key,))
        row = await cur.fetchone()
        return dict(row) if row else None
```

- [ ] **步骤 4：运行测试确认通过**

运行：`pytest tests/test_edit_lease.py -v`
预期：PASS（5 passed）

- [ ] **步骤 5：Commit**

```bash
git add api/db/lease_store.py tests/test_edit_lease.py
git commit -m "feat(db): 新增 SQLite 租约锁 LeaseStore + 排他/续租/释放测试"
```

---

## 任务 4：Engine 接入持久化队列 + SSE 广播增强

**文件：**
- 修改：`api/worker/engine.py`
- 测试：`tests/test_persistent_queue.py`（已有，验证新行为）

- [ ] **步骤 1：修改 Engine init/start**

在 `__init__` 中改用 `QueueStore`：

```python
from ..db.queue_store import QueueStore

if self._persistent_queue:
    self._queue_db_queue = QueueStore(config.IF_PERSISTENT_QUEUE_DB)
```

将原有 `self._queue_db: QueueDB` 替换为：

```python
self._queue_db = QueueStore(config.IF_PERSISTENT_QUEUE_DB) if self._persistent_queue else None
```

并在 `start()` 里 `await self._queue_db.open()`（若使用）。注意 `_queue_db.enqueue / list_pending / mark_completed` 调用签名保持不变（复用 QueueStore 方法）。

- [ ] **步骤 2：submit_priority 入队落盘**

在 `submit_priority` 中，原：

```python
if self._persistent_queue and self._queue_db:
    self._queue_db.enqueue(task_id, priority, seq)
```

保持不变（QueueStore 提供同名 enqueue）。但需确认 `_queue_db` 连接已在 start() 打开，否则在首次 submit 时自动 open（QueueStore.enqueue 内部调 open()）。

- [ ] **步骤 3：SSE 广播增强（入队位置）**

在 `submit_priority` 中，将入队位置从「提交前推导」改为「提交后精确值」：

```python
# v4.2: SSE 事件 - 任务已入队（含队列位置）
try:
    from .sse_events import publish_task_event
    publish_task_event(task_id, "status", {
        "task_id": task_id, "status": "pending", "queue_pos": pos,
    })
except Exception:
    pass
```

保持现有逻辑，但计算 `pos` 改为落盘后、入队成功后。同时补充 `priority` 字段：

```python
publish_task_event(task_id, "status", {
    "task_id": task_id, "status": "pending", "queue_pos": pos,
    "priority": priority,
})
```

- [ ] **步骤 4：运行持久化队列相关测试**

运行：`pytest tests/test_persistent_queue.py -v`
预期：PASS

- [ ] **步骤 5：运行全部队列测试**

运行：`pytest tests/test_priority_queue.py tests/test_persistent_queue.py -v`
预期：PASS

- [ ] **步骤 6：Commit**

```bash
git add api/worker/engine.py
git commit -m "feat(engine): 队列入队瞬时 WAL 落盘 + SSE 广播带 priority/queue_pos"
```

---

## 任务 5：dispatch_edit 接入租约锁（可切换）

**文件：**
- 修改：`api/dispatch_edit.py`
- 测试：`tests/test_edit_mutex.py`（已有）+ `tests/test_edit_lease.py`（新增）

- [ ] **步骤 1：导入 LeaseStore 与配置**

```python
from .db.lease_store import LeaseStore
```

并实例化模块级：

```python
_EDIT_LEASE_STORE = LeaseStore(os.path.join(os.path.dirname(config.DB_FILE) or ".", "data", "edit_leases.db"))
```

- [ ] **步骤 2：新增租约锁获取/释放/续租逻辑**

```python
async def _acquire_edit_lock(key: str, holder: str, timeout: float | None = None) -> str | None:
    """按配置选择：租约锁 或 文件锁。返回持有 token；获取失败返回 None。"""
    if config.EDIT_LEASE_ENABLED:
        deadline = time.monotonic() + timeout if timeout is not None else None
        token = uuid.uuid4().hex
        while True:
            if deadline is not None and time.monotonic() > deadline:
                return None
            ok = await _EDIT_LEASE_STORE.acquire(key, holder, token, config.EDIT_LEASE_TTL)
            if ok:
                return token
            await asyncio.sleep(1.0)
    # 兼容旧文件锁
    return await _acquire_edit_mutex(key, timeout)


async def _renew_edit_lock_loop(key: str, token: str) -> asyncio.Task:
    """持锁期间的心跳续租协程。"""
    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(config.EDIT_LEASE_TTL / 3.0)
            if not await _EDIT_LEASE_STORE.renew(key, token, config.EDIT_LEASE_TTL):
                return  # 锁已被抢/释放，停止续租
    t = asyncio.create_task(_heartbeat())
    return t


async def _release_edit_lock(key: str, token: str | None) -> None:
    if config.EDIT_LEASE_ENABLED and token:
        await _EDIT_LEASE_STORE.release(key, token)
    else:
        _release_edit_mutex(key, token)
```

- [ ] **步骤 3：修改 _run_edit_job 使用新锁**

替换 `_acquire_edit_mutex` / `_release_edit_mutex` 调用：

```python
async def _run_edit_job(job_id, image, ctype, prompt, download, model="default"):
    _EDIT_PENDING.add(job_id)
    holder = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
    try:
        proxy = await _EDIT_PROXY_POOL.acquire_proxy()
        key = proxy or "default"
        local_lock = _EDIT_PROXY_POOL.lock_for(key) if proxy else _EDIT_LOCK
        async with local_lock:
            token = await _acquire_edit_lock(key, holder)
            if not token:
                await db.mark_finished(job_id, "error", None,
                                 "图生图繁忙：其他实例正在生成同一出口通道，请稍后重试", None)
                return
            heartbeat = await _renew_edit_lock_loop(key, token)
            try:
                await _run_edit_chain(job_id, image, ctype, prompt, download, model, proxy)
            finally:
                heartbeat.cancel()
                await _release_edit_lock(key, token)
    finally:
        _EDIT_PROXY_POOL.release_proxy(proxy)
        _EDIT_PENDING.discard(job_id)
```

- [ ] **步骤 4：运行互斥/UAT 相关测试**

运行：`pytest tests/test_edit_mutex.py tests/test_edit_lease.py -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add api/dispatch_edit.py
git commit -m "feat(dispatch_edit): 图生图互斥锁可切换 SQLite 租约锁 + 自动续租/超时抢占"
```

---

## 任务 6：E2E 租约锁验证脚本

**文件：**
- 创建：`scripts/e2e_lease_lock.py`

- [ ] **步骤 1：编写 E2E 验证脚本**

```python
"""图生图租约锁 E2E 验证：并发竞争同一 key，仅一个持有者成功。

用法：
    python scripts/e2e_lease_lock.py            # 使用临时 DB
    IF_EDIT_LEASE_ENABLED=1 python -m pytest tests/test_edit_lease.py -v
"""
import asyncio
import os
import tempfile
import time
import uuid

os.environ.setdefault("IF_ACCOUNT_AUTO", "0")
os.environ.setdefault("IF_MOCK_REGISTER", "1")
os.environ["IF_EDIT_LEASE_ENABLED"] = "1"

from api import config
from api.dispatch_edit import _acquire_edit_lock, _release_edit_lock


async def main() -> None:
    key = "e2e-lease-key"
    holder_a, holder_b = "proc-A", "proc-B"
    tok_a = await _acquire_edit_lock(key, holder_a, timeout=3.0)
    assert tok_a, "holder A 应获得锁"
    print(f"[OK] holder A 获取锁: {tok_a[:8]}")

    tok_b = await _acquire_edit_lock(key, holder_b, timeout=1.5)
    assert tok_b is None, "holder B 在 A 持有期间应拿不到锁"
    print("[OK] holder B 被阻塞")

    await _release_edit_lock(key, tok_a)
    tok_c = await _acquire_edit_lock(key, holder_b, timeout=3.0)
    assert tok_c, "holder A 释放后 B 应能获取锁"
    print(f"[OK] holder B 在释放后获取锁: {tok_c[:8]}")
    await _release_edit_lock(key, tok_c)

    # 异常宕机模拟：不释放直接丢弃 → 无续租 → TTL 后过期
    tok_d = await _acquire_edit_lock(key, "holder-C", timeout=3.0)
    assert tok_d
    # 不释放，模拟崩溃
    await asyncio.sleep(config.EDIT_LEASE_TTL + 1)
    tok_e = await _acquire_edit_lock(key, "holder-D", timeout=3.0)
    assert tok_e, "无续租的锁应在 TTL 后自动过期"

    print(f"[OK] 异常宕机后锁自动过期，holder D 获取锁: {tok_e[:8]}")
    print("E2E 租约锁验证全部通过 ✅")


if __name__ == "__main__":
    os.environ["IF_DB_FILE"] = tempfile.mktemp(suffix=".db")
    asyncio.run(main())
```

- [ ] **步骤 2：运行 E2E 脚本**

运行：`python scripts/e2e_lease_lock.py`
预期：全部 `[OK]` 行输出，退出码 0

- [ ] **步骤 3：Commit**

```bash
git add scripts/e2e_lease_lock.py
git commit -m "test: 图生图租约锁 E2E 验证脚本"
```

---

## 任务 7：同步 deploy 目录 & 全体回归

**文件：**
- 修改：`deploy/api/db.py`, `deploy/api/worker/engine.py`, `deploy/api/dispatch_edit.py` 等（通过 sync 脚本）

- [ ] **步骤 1：运行 sync_deploy**

运行：`python scripts/sync_deploy.py sync`
预期：同步成功，无冲突报错

- [ ] **步骤 2：全量测试回归**

运行：`pytest tests/ -v --timeout=60 2>&1 | tail -30`
预期：无新增失败

- [ ] **步骤 3：冒烟启动**

运行：`python -c "from api.main import app; print('import ok')"`
预期：import ok

- [ ] **步骤 4：Commit**

```bash
git add deploy/ api/
git commit -m "chore(deploy): 同步租约锁与持久化队列到 deploy 目录"
```

---

## 自检结果

- **规格覆盖度**：三层有界队列（已有 CountedPriorityQueue，本计划验证+落盘增强）✓；入队瞬时落盘（QueueStore.submit_priority）✓；SSE 广播（任务 4 步骤 3）✓；SQLite Lease Lock 排他/续租/超时抢占（任务 3+5）✓；异常宕机自动释放（测试 + E2E 步骤）✓
- **占位符扫描**：无 TODO/待定
- **类型一致性**：`LeaseStore.acquire(key, holder, token, ttl)` / `renew(key, token, new_ttl)` / `release(key, token)` 签名在任务 1-5 一致；`_acquire_edit_lock(key, holder, timeout)` / `_release_edit_lock(key, token)` 在任务 5-6 一致
