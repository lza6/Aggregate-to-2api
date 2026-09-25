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

supersede 语义（v14 P3，参考 agentmemory 巩固蓝本 isLatest + supersedes）：
- 同 (user_key, scene, content) 再次巩固出 L1 原子事实时，旧 L1 记录标记 superseded_by=新记录 id
- query() 默认过滤 superseded_by IS NULL（不返回被取代记录；旧数据列缺失时降级不过滤不崩）

开关：IF_MEMORY_CONSOLIDATION_ENABLED=0 关闭，回退无记忆（零回归）。
三档衰减开关：IF_MEMORY_APPLY_DECAY（缺省关 0）→ consolidate 尾部可选挂载 apply_decay()。
LLM 调用：巩固压缩默认真实调用 tryingopen。IF_MOCK_UPSTREAM=1 时走本地去重。

数据层：复用现有 SQLite（imagefree.db），加 4 张表（不改 requests/chat_usage schema）。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field

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

# hot/warm/cold 三档衰减（v14 P3，参考 agentmemory applyDecay）：
# hot：距上次访问 < 1d → importance 提分（+0.05，钳 1.0）；warm：1d ~ 各层阈值之间 → 不动；
# cold：超 _DECAY_THRESHOLDS → 淘汰（复用 _prune_stale）
_HOT_RECENT_SECONDS = 1 * 86400
_HOT_BOOST = 0.05
_HOT_TABLES = ("mem_observations", "mem_atoms", "mem_scenarios", "mem_persona")

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
    superseded_by: int | None = None  # v14 P3：被同 (user_key, scene, content) 的新 L1 取代时指向新记录 id
    explain: list[str] = field(default_factory=list)  # B4/P1-1：命中理由（importance/新鲜度），前端「为什么命中」



def _rrf_merge(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion：多路排序融合（v18 P0-2，ai-memory/mem0 对标）。

    对每路排名列表（rank 1 起）累计 1/(k+rank) 得分；返回 {rowid: score}。
    空输入返回 {}。
    """
    scores: dict[int, float] = {}
    for rank_list in rankings:
        for i, rid in enumerate(rank_list):
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + i + 1)
    return scores


def _fts_match_expr(query: str, max_terms: int = 8) -> str:
    """查询串 → FTS5 MATCH 表达式（空格分词 + OR，防注入：仅放行 \"引号包裹词\"）。"""
    toks = [tok for tok in query.replace('"', " ").split() if tok][:max_terms]
    if not toks:
        return '""'
    return " OR ".join(f'"{tok}"' for tok in toks)


def _build_explain(r, now: float) -> list[str]:
    """构造单条记忆命中理由（B4/P1-1，纯 Python 零 DB 开销）。"""
    reasons: list[str] = []
    importance = float(r["importance"])
    if importance >= 0.8:
        reasons.append("importance 高（>=0.8），优先命中")
    elif importance >= 0.6:
        reasons.append("importance 中等（0.6-0.8）")
    else:
        reasons.append("importance 普通（<0.6）")
    age = now - float(r["last_accessed_at"])
    if age < 86400:
        reasons.append("近期访问过（<1 天，hot 记忆）")
    elif age < 7 * 86400:
        reasons.append("一周内访问过")
    else:
        reasons.append("较久未访问")
    if "superseded_by" in r.keys() and r["superseded_by"] is None:  # noqa: SIM118 - sqlite3.Row 的 in 判值非键
        reasons.append("当前有效（未被取代）")
    return reasons

class MemoryStore:
    """四层记忆存储 + 异步巩固管道。"""

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._consolidation_task: asyncio.Task | None = None
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        """同步连接：isolation_level=None + WAL + busy_timeout（对齐主流程 Do-Not-Repeat#1）。

        默认 fallback journal + 隐式事务会让本 store 与 ip_blocklist 等共享库
        跨写锁窗口拉长（全量并发偶发 database is locked）；isolation_level=None
        + WAL 与 api/db/core.py/ip_blocklist_store.py 一致。
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL").fetchone()  # 消费结果防 "statements in progress"
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
            # v14 P3 幂等迁移：旧库无 superseded_by 列 → ADD COLUMN（duplicate column 报错吞掉）。
            # 仅 mem_atoms 需要 supersede 语义（L1 原子事实被同 content 新原子取代）；其余层不动。
            try:
                conn.execute("ALTER TABLE mem_atoms ADD COLUMN superseded_by INTEGER")
            except sqlite3.OperationalError as exc:
                if "duplicate column" not in str(exc).lower():
                    raise
            # v18 P0-2：mem_atoms FTS5 虚表 + 同步触发器（RRF 检索用；幂等，存量数据由 rebuild 补齐）
            conn.executescript(
                '''
                CREATE VIRTUAL TABLE IF NOT EXISTS mem_atoms_fts USING fts5(
                    content, content='mem_atoms', content_rowid='id', tokenize='unicode61'
                );
                CREATE TRIGGER IF NOT EXISTS mem_atoms_fts_ai AFTER INSERT ON mem_atoms BEGIN
                    INSERT INTO mem_atoms_fts(rowid, content) VALUES (new.id, new.content);
                END;
                CREATE TRIGGER IF NOT EXISTS mem_atoms_fts_ad AFTER DELETE ON mem_atoms BEGIN
                    INSERT INTO mem_atoms_fts(mem_atoms_fts, rowid, content) VALUES('delete', old.id, old.content);
                END;
                CREATE TRIGGER IF NOT EXISTS mem_atoms_fts_au AFTER UPDATE OF content ON mem_atoms BEGIN
                    INSERT INTO mem_atoms_fts(mem_atoms_fts, rowid, content) VALUES('delete', old.id, old.content);
                    INSERT INTO mem_atoms_fts(rowid, content) VALUES (new.id, new.content);
                END;
                '''
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

    def _has_column(self, table: str, column: str) -> bool:
        """检查表是否有某列（PRAGMA table_info；供 query 降级判断）。"""
        with self._conn() as conn:
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        return column in cols

    async def query(
        self,
        user_key: str,
        scene: str,
        layer: str = "L1",
        limit: int = 10,
        mode: str = "auto",
    ) -> list[MemoryRecord]:
        """查询某层记忆（供 chat 端点注入上下文）。

        v14 P3 supersede：mem_atoms 查询默认过滤 superseded_by IS NULL（被取代的旧 L1
        不返回）。保底：旧库列缺失时降级不过滤（不崩，向后兼容）。
        v18 P0-2 RRF：mode=auto 时按 IF_MEMORY_RRF 决定（缺省纯 SQL 零回归）；mode=rrf 强制
        双路融合（importance 排序 + FTS5 BM25）；FTS 不可用自动降级纯 SQL。
        """
        table = {"L0": "mem_observations", "L1": "mem_atoms", "L2": "mem_scenarios", "L3": "mem_persona"}.get(layer)
        if not table:
            return []

        rrf_enabled = mode == "rrf"
        if mode == "auto":
            try:
                from ..config import get_settings

                rrf_enabled = bool(get_settings().if_memory_rrf)
            except Exception:  # noqa: BLE001
                rrf_enabled = False

        # supersede 过滤：仅 L1（mem_atoms）且列存在；列缺失降级不过滤
        supersede_filter = ""
        if table == "mem_atoms" and self._has_column(table, "superseded_by"):
            supersede_filter = " AND superseded_by IS NULL"

        def _query() -> list[MemoryRecord]:
            now = time.time()
            with self._conn() as conn:
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE user_key=? AND scene=?{supersede_filter} "
                    "ORDER BY importance DESC, last_accessed_at DESC LIMIT ?",
                    (user_key, scene, limit),
                ).fetchall()
                plain_records = [
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
                        # sqlite3.Row 的 `in` 只匹配值不匹配键；必须用 r.keys() 判定列存在
                        superseded_by=r["superseded_by"] if "superseded_by" in r.keys() else None,  # noqa: SIM118 - sqlite3.Row 的 in 判值非键
                        explain=_build_explain(r, now),
                    )
                    for r in rows
                ]
                if not rrf_enabled or table != "mem_atoms":
                    return plain_records
                # RRF 双路：importance 排序（top 50）+ FTS5 BM25（top 50，场景过滤）
                try:
                    imp_rank = [
                        r[0]
                        for r in conn.execute(
                            f"SELECT id FROM {table} WHERE user_key=? AND scene=?{supersede_filter} "
                            "ORDER BY importance DESC, last_accessed_at DESC LIMIT 50",
                            (user_key, scene),
                        ).fetchall()
                    ]
                    fts_rank: list[int] = []
                    if len(plain_records) < limit:
                        # 仅当结果不足时才用 FTS 扩充（BM25 相关词召回）
                        fts_rows = conn.execute(
                            "SELECT a.id FROM mem_atoms_fts f JOIN mem_atoms a ON a.id = f.rowid "
                            "WHERE a.user_key=? AND a.scene=?" + (" AND a.superseded_by IS NULL" if "superseded_by IS NULL" in supersede_filter else "") + " "
                            "AND mem_atoms_fts MATCH ? ORDER BY bm25(mem_atoms_fts) LIMIT 50",
                            (user_key, scene, _fts_match_expr(scene + " " + user_key)),
                        ).fetchall()
                        fts_rank = [r[0] for r in fts_rows]
                    merged = _rrf_merge([imp_rank, fts_rank])
                except sqlite3.OperationalError:
                    merged = {}
                if not merged:
                    return plain_records
                top_ids = [rid for rid, _ in sorted(merged.items(), key=lambda kv: kv[1], reverse=True)[:limit]]
                if not top_ids:
                    return plain_records
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE id IN ({','.join('?' * len(top_ids))})",
                    tuple(top_ids),
                ).fetchall()
                by_id = {r["id"]: r for r in rows}
                records: list[MemoryRecord] = []
                for rid in top_ids:
                    r = by_id.get(rid)
                    if r is None:
                        continue
                    records.append(MemoryRecord(
                        id=r["id"],
                        layer=layer,
                        user_key=r["user_key"],
                        scene=r["scene"],
                        content=r["content"],
                        importance=r["importance"],
                        created_at=r["created_at"],
                        last_accessed_at=r["last_accessed_at"],
                        source_ids=r["source_ids"],
                        superseded_by=r["superseded_by"] if "superseded_by" in r.keys() else None,  # noqa: SIM118 - sqlite3.Row 的 in 判值非键
                        explain=_build_explain(r, now) + [f"RRF 融合命中（id={rid}）"],
                    ))
                return records

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
        from ..config import get_settings

        mock_upstream = get_settings().if_mock_upstream
        if mock_upstream:
            result = await self._consolidate_mock()
        else:
            # 真实 LLM 路径：调 tryingopen 上游压缩（用户批准后启用）
            try:
                result = await self._consolidate_with_llm()
            except Exception as exc:
                log.warning("LLM 记忆巩固失败，回退 Mock: %s", exc)
                result = await self._consolidate_mock()
        # v14 P3：可选三档衰减挂载（IF_MEMORY_APPLY_DECAY 缺省关，零行为变化）
        if get_settings().if_memory_apply_decay:
            result["decay"] = await self.apply_decay()
        return result

    async def _consolidate_mock(self) -> dict[str, int]:
        """Mock 巩固：去重 + importance>=0.6 筛选（不调 LLM）。

        v14 P3 supersede：写入 L1 前先把同 (user_key, scene, content) 的旧 L1 记录
        标记 superseded_by=新记录 id（先插新行拿 id，再回填旧行，保证链路可追溯）。
        """
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
                    # importance>=0.6 的写入 L1；同 content 旧 L1 标记 superseded
                    promoted = 0
                    superseded_total = 0
                    for item in seen.values():
                        if item["importance"] >= 0.6:
                            cur = conn.execute(
                                "INSERT INTO mem_atoms(user_key, scene, content, importance, created_at, last_accessed_at, source_ids) "
                                "VALUES(?,?,?,?,?,?,?)",
                                (
                                    item["user_key"],
                                    item["scene"],
                                    item["content"],
                                    item["importance"],
                                    now,
                                    now,
                                    str(item["id"]),
                                ),
                            )
                            new_id = cur.lastrowid or 0
                            mark = conn.execute(
                                "UPDATE mem_atoms SET superseded_by=? WHERE superseded_by IS NULL "
                                "AND id<>? AND user_key=? AND scene=? AND content=?",
                                (new_id, new_id, item["user_key"], item["scene"], item["content"]),
                            )
                            superseded_total += mark.rowcount or 0
                            promoted += 1
                    # 清空已巩固的 L0（避免重复巩固）
                    conn.execute("DELETE FROM mem_observations")
                    # 衰减淘汰超期记忆
                    pruned = self._prune_stale(conn, now)
                    conn.commit()
                    return {"L0_to_L1": promoted, "pruned": pruned, "superseded": superseded_total}

            return await asyncio.to_thread(_run)

    async def _consolidate_with_llm(self) -> dict[str, int]:
        """真实 LLM 巩固：用 tryingopen 上游压缩 L0→L1。"""
        from .metrics import inc_llm_call, inc_memory_consolidation

        # 取 L0 待巩固记录
        async with self._lock:

            def _fetch() -> list:
                with self._conn() as conn:
                    return [
                        dict(r)
                        for r in conn.execute(
                            "SELECT id, user_key, scene, content, importance FROM mem_observations"
                        ).fetchall()
                    ]

            rows = await asyncio.to_thread(_fetch)
        if not rows:
            inc_memory_consolidation("fallback")
            return {"L0_to_L1": 0, "pruned": 0}

        # 调 tryingopen 上游压缩（用户批准后才启用，付费 API 红线）
        try:
            from ..providers.registry import bootstrap, registry

            bootstrap()
            chat_models = registry.all_chat_models()
            if not chat_models:
                inc_memory_consolidation("fallback")
                return await self._consolidate_mock()
            model_id = chat_models[0].id
            provider = registry.chat_providers.get(model_id.split("/", 1)[0])
            if provider is None:
                inc_memory_consolidation("fallback")
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
                inc_llm_call("memory", "consolidate")
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

                            def _insert(content=content, scene=scene, imp=imp, items=items) -> int:
                                with self._conn() as conn:
                                    cur = conn.execute(
                                        "INSERT INTO mem_atoms(user_key, scene, content, importance, created_at, last_accessed_at, source_ids) "
                                        "VALUES(?,?,?,?,?,?,?)",
                                        (
                                            items[0]["user_key"],
                                            scene,
                                            content.strip(),
                                            imp,
                                            now,
                                            now,
                                            ",".join(str(i["id"]) for i in items),
                                        ),
                                    )
                                    # v14 P3 supersede：同 (user_key, scene, content) 旧 L1 标记被取代
                                    new_id = cur.lastrowid or 0
                                    conn.execute(
                                        "UPDATE mem_atoms SET superseded_by=? WHERE superseded_by IS NULL "
                                        "AND id<>? AND user_key=? AND scene=? AND content=?",
                                        (new_id, new_id, items[0]["user_key"], scene, content.strip()),
                                    )
                                    conn.commit()
                                    return new_id

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
            inc_memory_consolidation("success")
            return {"L0_to_L1": promoted, "pruned": 0}
        except Exception as exc:
            inc_memory_consolidation("llm_error")
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

    async def apply_decay(self) -> dict[str, int]:
        """v14 P3：hot/warm/cold 三档衰减（供 consolidation loop 调用，可选挂入 consolidate 尾部）。

        - hot：距上次访问 < 1d → importance 提分（+_HOT_BOOST，钳 1.0；hot 记忆加权保活跃）
        - warm：1d ~ 各层 _DECAY_THRESHOLDS 之间 → 不动（保持现状）
        - cold：超 _DECAY_THRESHOLDS → 淘汰（复用 _prune_stale 删除）

        返回各档处理条数（hot_boosted / cold_pruned）。
        """
        now = time.time()
        async with self._lock:

            def _run() -> dict[str, int]:
                with self._conn() as conn:
                    # hot 档：最近 1d 内访问过的记忆提分（全层；warm/cold 不动）
                    boosted = 0
                    for table in _HOT_TABLES:
                        cur = conn.execute(
                            f"UPDATE {table} SET importance = MIN(1.0, importance + ?) WHERE last_accessed_at >= ?",
                            (_HOT_BOOST, now - _HOT_RECENT_SECONDS),
                        )
                        boosted += cur.rowcount or 0
                    # cold 档：超期未访问淘汰（_prune_stale 按各层阈值删）
                    pruned = self._prune_stale(conn, now)
                    conn.commit()
                    return {"hot_boosted": boosted, "cold_pruned": pruned}

            return await asyncio.to_thread(_run)

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
