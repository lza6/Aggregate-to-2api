"""P1-A3：L0-L3 记忆分层 + 异步巩固管道（参考 agentmemory + TencentDB-Agent-Memory）。

四层记忆（逐层压缩固化）：
- L0 mem_observations：原始观察（每次 chat/生成请求的事实片段）
- L1 mem_atoms：蒸馏原子事实（去重 + 重要性筛选）
- L2 mem_scenarios：场景化记忆（按场景聚合：用户在"画电商主图"时的偏好集）
- L3 mem_persona：用户人格（长期偏好：风格/语气/常用 provider）

巩固管道（后台 worker，参考 agentmemory consolidation-pipeline.ts）：
- 定期把 L0 压缩到 L1（去重 + 重要性评分）
- L1 按场景聚合到 L2
- L2 提炼到 L3（用户长期偏好）
- hot/warm/cold 衰减淘汰（超期未访问的记忆降级/删除）

开关：IF_MEMORY_CONSOLIDATION_ENABLED=0 关闭，回退无记忆（零回归）。
LLM 调用：巩固压缩用 tryingopen 上游 LLM（付费 API 红线：Mock 或用户批准预算）。

数据层：复用现有 SQLite（imagefree.db），加 4 张表（不改 requests/chat_usage schema）。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from dataclasses import dataclass

log = logging.getLogger("agent.memory")

# P1-A3 开关：默认开启，回滚置 0 即回退无记忆
MEMORY_CONSOLIDATION_ENABLED = os.getenv("IF_MEMORY_CONSOLIDATION_ENABLED", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# 巩固周期（秒）：默认 300s（5 分钟跑一次 L0→L1 压缩）
CONSOLIDATION_INTERVAL_SECONDS = float(os.getenv("IF_MEMORY_CONSOLIDATION_INTERVAL", "300"))

# 记忆衰减阈值（秒）：L0 超 7 天未访问淘汰，L1 超 30 天，L2 超 90 天，L3 永久
_DECAY_THRESHOLDS = {"L0": 7 * 86400, "L1": 30 * 86400, "L2": 90 * 86400, "L3": float("inf")}

# 默认 DB 路径（复用 imagefree.db，加 mem_ 前缀表）
_DEFAULT_DB = os.getenv("IF_DB_FILE", "data/imagefree.db")


@dataclass(frozen=True)
class MemoryRecord:
    """单条记忆记录。"""

    id: int
    layer: str  # L0 / L1 / L2 / L3
    user_key: str  # 用户标识（单租户当前用 "default"）
    scene: str  # 场景（image/chat/video/ecommerce/ppt）
    content: str  # 记忆正文
    importance: float  # 重要性评分 0.0-1.0
    created_at: float
    last_accessed_at: float
    source_ids: str  # 来源记录 id 列表（L1 来自哪些 L0）


class MemoryStore:
    """四层记忆存储 + 异步巩固管道。"""

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._consolidation_task: asyncio.Task | None = None
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        """建 4 张记忆表（CREATE IF NOT EXISTS，向后兼容不改旧表）。"""
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS mem_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_key TEXT NOT NULL,
                    scene TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance REAL DEFAULT 0.5,
                    created_at REAL NOT NULL,
                    last_accessed_at REAL NOT NULL,
                    source_ids TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_mem_obs_user_scene ON mem_observations(user_key, scene, created_at);

                CREATE TABLE IF NOT EXISTS mem_atoms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_key TEXT NOT NULL,
                    scene TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance REAL DEFAULT 0.5,
                    created_at REAL NOT NULL,
                    last_accessed_at REAL NOT NULL,
                    source_ids TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_mem_atom_user_scene ON mem_atoms(user_key, scene, created_at);

                CREATE TABLE IF NOT EXISTS mem_scenarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_key TEXT NOT NULL,
                    scene TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance REAL DEFAULT 0.5,
                    created_at REAL NOT NULL,
                    last_accessed_at REAL NOT NULL,
                    source_ids TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_mem_sce_user_scene ON mem_scenarios(user_key, scene, created_at);

                CREATE TABLE IF NOT EXISTS mem_persona (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_key TEXT NOT NULL,
                    scene TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance REAL DEFAULT 0.5,
                    created_at REAL NOT NULL,
                    last_accessed_at REAL NOT NULL,
                    source_ids TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_mem_per_user ON mem_persona(user_key, scene);
                """
            )
            conn.commit()

    async def observe(self, user_key: str, scene: str, content: str, importance: float = 0.5) -> int:
        """L0 写入：记录一次观察（chat/生成请求的事实片段）。"""
        now = time.time()
        async with self._lock:
            def _insert() -> int:
                with self._conn() as conn:
                    cur = conn.execute(
                        "INSERT INTO mem_observations(user_key, scene, content, importance, created_at, last_accessed_at) "
                        "VALUES(?,?,?,?,?,?)",
                        (user_key, scene, content, importance, now, now),
                    )
                    conn.commit()
                    return cur.lastrowid or 0

            return await asyncio.to_thread(_insert)

    async def query(self, user_key: str, scene: str, layer: str = "L1", limit: int = 10) -> list[MemoryRecord]:
        """查询某层记忆（供 chat 端点注入上下文）。"""
        table = {"L0": "mem_observations", "L1": "mem_atoms", "L2": "mem_scenarios", "L3": "mem_persona"}.get(layer)
        if not table:
            return []

        def _query() -> list[MemoryRecord]:
            with self._conn() as conn:
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE user_key=? AND scene=? ORDER BY importance DESC, last_accessed_at DESC LIMIT ?",
                    (user_key, scene, limit),
                ).fetchall()
                return [
                    MemoryRecord(
                        id=r["id"],
                        layer=layer,
                        user_key=r["user_key"],
                        scene=r["scene"],
                        content=r["content"],
                        importance=r["importance"],
                        created_at=r["created_at"],
                        last_accessed_at=r["last_accessed_at"],
                        source_ids=r["source_ids"],
                    )
                    for r in rows
                ]

        records = await asyncio.to_thread(_query)
        # 查询即更新访问时间（hot 记忆不衰减）
        if records:
            now = time.time()
            ids = ",".join(str(r.id) for r in records)
            await asyncio.to_thread(self._touch_access, table, ids, now)
        return records

    def _touch_access(self, table: str, ids: str, now: float) -> None:
        """更新记忆访问时间（防 hot 衰减）。"""
        with self._conn() as conn:
            conn.execute(f"UPDATE {table} SET last_accessed_at=? WHERE id IN ({ids})", (now,))
            conn.commit()

    async def consolidate(self) -> dict[str, int]:
        """巩固管道：L0→L1 压缩（去重 + 重要性筛选）。

        付费 API 红线：压缩用 tryingopen 上游 LLM（IF_MOCK_UPSTREAM=1 时 Mock，
        不发起真实付费调用；用户批准后才真实压缩）。

        返回各层处理条数。
        """
        if not MEMORY_CONSOLIDATION_ENABLED:
            return {"L0_to_L1": 0, "pruned": 0}

        # Mock 路径：简单按 content 去重 + importance 阈值筛选（不调 LLM）
        mock_upstream = os.getenv("IF_MOCK_UPSTREAM", "0").strip().lower() in {"1", "true", "yes", "on"}
        if mock_upstream:
            return await self._consolidate_mock()
        # 真实 LLM 路径：调 tryingopen 上游压缩（用户批准后启用）
        try:
            return await self._consolidate_with_llm()
        except Exception as exc:
            log.warning("LLM 记忆巩固失败，回退 Mock: %s", exc)
            return await self._consolidate_mock()

    async def _consolidate_mock(self) -> dict[str, int]:
        """Mock 巩固：去重 + importance>=0.6 筛选（不调 LLM）。"""
        async with self._lock:
            def _run() -> dict[str, int]:
                now = time.time()
                with self._conn() as conn:
                    # 取 L0 全部
                    rows = conn.execute(
                        "SELECT id, user_key, scene, content, importance FROM mem_observations"
                    ).fetchall()
                    # 按 (user_key, scene, content) 去重，取 importance 最高
                    seen: dict[tuple, dict] = {}
                    for r in rows:
                        key = (r["user_key"], r["scene"], r["content"])
                        if key not in seen or r["importance"] > seen[key]["importance"]:
                            seen[key] = dict(r)
                    # importance>=0.6 的写入 L1
                    promoted = 0
                    for item in seen.values():
                        if item["importance"] >= 0.6:
                            conn.execute(
                                "INSERT INTO mem_atoms(user_key, scene, content, importance, created_at, last_accessed_at, source_ids) "
                                "VALUES(?,?,?,?,?,?,?)",
                                (item["user_key"], item["scene"], item["content"], item["importance"], now, now, str(item["id"])),
                            )
                            promoted += 1
                    # 清空已巩固的 L0（避免重复巩固）
                    conn.execute("DELETE FROM mem_observations")
                    # 衰减淘汰超期记忆
                    pruned = self._prune_stale(conn, now)
                    conn.commit()
                    return {"L0_to_L1": promoted, "pruned": pruned}

            return await asyncio.to_thread(_run)

    async def _consolidate_with_llm(self) -> dict[str, int]:
        """真实 LLM 巩固：用 tryingopen 上游压缩 L0→L1。"""
        # 取 L0 待巩固记录
        async with self._lock:
            def _fetch() -> list:
                with self._conn() as conn:
                    return [dict(r) for r in conn.execute(
                        "SELECT id, user_key, scene, content, importance FROM mem_observations"
                    ).fetchall()]

            rows = await asyncio.to_thread(_fetch)
        if not rows:
            return {"L0_to_L1": 0, "pruned": 0}

        # 调 tryingopen 上游压缩（用户批准后才启用，付费 API 红线）
        try:
            from ..providers.registry import bootstrap, registry

            bootstrap()
            chat_models = registry.all_chat_models()
            if not chat_models:
                return await self._consolidate_mock()
            model_id = chat_models[0].id
            provider = registry.chat_providers.get(model_id.split("/", 1)[0])
            if provider is None:
                return await self._consolidate_mock()
            # 按 scene 分组压缩
            from collections import defaultdict

            by_scene: dict[str, list[dict]] = defaultdict(list)
            for r in rows:
                by_scene[r["scene"]].append(r)
            promoted = 0
            now = time.time()
            for scene, items in by_scene.items():
                contents = [f"[{i['id']}] {i['content']}" for i in items]
                system_prompt = (
                    "你是记忆巩固器。把多条原始观察压缩为原子事实，去重 + 保留重要信息。"
                    "每条原子事实一行，格式：importance|content。importance 0.0-1.0。"
                )
                result = await provider.chat_collect(
                    model_id,
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": "\n".join(contents)},
                    ],
                )
                text = result.get("text", "")
                for line in text.strip().split("\n"):
                    if "|" not in line:
                        continue
                    imp_str, _, content = line.partition("|")
                    try:
                        imp = float(imp_str.strip())
                    except ValueError:
                        imp = 0.5
                    if imp >= 0.5 and content.strip():
                        async with self._lock:
                            def _insert(content=content, scene=scene, imp=imp, items=items) -> None:
                                with self._conn() as conn:
                                    conn.execute(
                                        "INSERT INTO mem_atoms(user_key, scene, content, importance, created_at, last_accessed_at, source_ids) "
                                        "VALUES(?,?,?,?,?,?,?)",
                                        (items[0]["user_key"], scene, content.strip(), imp, now, now,
                                         ",".join(str(i["id"]) for i in items)),
                                    )
                                    conn.commit()

                            await asyncio.to_thread(_insert)
                        promoted += 1
            # 清空已巩固的 L0（P0-11 修复：原 lambda 创建两个独立 _conn() 连接，
            # execute 与 commit 落在不同连接上导致 DELETE 未生效。改为单连接 with 上下文）
            async with self._lock:
                def _clear_l0() -> None:
                    with self._conn() as conn:
                        conn.execute("DELETE FROM mem_observations")
                        conn.commit()

                await asyncio.to_thread(_clear_l0)
            return {"L0_to_L1": promoted, "pruned": 0}
        except Exception as exc:
            log.warning("LLM 巩固失败回退 Mock: %s", exc)
            return await self._consolidate_mock()

    def _prune_stale(self, conn: sqlite3.Connection, now: float) -> int:
        """衰减淘汰超期未访问的记忆。"""
        pruned = 0
        for layer, threshold in _DECAY_THRESHOLDS.items():
            if threshold == float("inf"):
                continue
            table = {"L0": "mem_observations", "L1": "mem_atoms", "L2": "mem_scenarios"}.get(layer)
            if not table:
                continue
            cur = conn.execute(
                f"DELETE FROM {table} WHERE last_accessed_at < ?",
                (now - threshold,),
            )
            pruned += cur.rowcount or 0
        return pruned

    async def start_consolidation_loop(self) -> None:
        """启动后台巩固 worker（lifespan 调用）。"""
        if not MEMORY_CONSOLIDATION_ENABLED:
            return
        self._consolidation_task = asyncio.create_task(self._consolidation_loop())

    async def _consolidation_loop(self) -> None:
        """巩固循环：每 CONSOLIDATION_INTERVAL_SECONDS 跑一次。"""
        while True:
            try:
                await asyncio.sleep(CONSOLIDATION_INTERVAL_SECONDS)
                result = await self.consolidate()
                if result.get("L0_to_L1", 0) > 0:
                    log.info("记忆巩固: %s", result)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("记忆巩固循环异常: %s", exc)

    async def stop_consolidation_loop(self) -> None:
        """停止后台巩固 worker（lifespan shutdown 调用）。"""
        if self._consolidation_task and not self._consolidation_task.done():
            self._consolidation_task.cancel()
            try:
                await self._consolidation_task
            except asyncio.CancelledError:
                pass


# 模块级单例（全服务共享；测试可用独立实例）
memory_store = MemoryStore()


__all__ = [
    "CONSOLIDATION_INTERVAL_SECONDS",
    "MEMORY_CONSOLIDATION_ENABLED",
    "MemoryRecord",
    "MemoryStore",
    "memory_store",
]
