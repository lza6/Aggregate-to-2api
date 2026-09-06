"""向量存储（sqlite-vec 优先，纯 Python 线性扫描降级）。

设计：
- 独立 aiosqlite 连接到 ``data/vectors.db``（不侵入主 DB schema/连接池）
- sqlite-vec 可用时：用 vec0 虚拟表做 KNN 检索（O(log n)）
- sqlite-vec 不可用时：降级为纯 Python 线性扫描 + cosine_similarity（O(n)，小规模够用）
- embedding BLOB 存主表 ``task_vectors``，vec0 虚拟表存 rowid→embedding 做检索
- 去重标记：``is_duplicate`` + ``duplicate_of``（不删除原图，仅标记）

公共接口：
- ``VectorStore`` 单例（通过 ``get_vector_store()`` 获取，测试可 ``reset_vector_store()``）
- ``upsert(task_id, prompt, ...)``：入库时写向量
- ``similar_search(task_id, top_k)``：KNN 检索
- ``find_duplicate(embedding, threshold)``：入库前查重
- ``mark_duplicate(task_id, duplicate_of)``：标记重复
- ``list_duplicates()``：列出所有重复项
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import aiosqlite

from .. import config
from . import embed

log = logging.getLogger("vector")

# ── sqlite-vec 可用性探测（进程级缓存）──────────────────────
_vec_available: bool | None = None


def _detect_vec_available() -> bool:
    """探测 sqlite-vec 是否可用（import + 加载扩展到内存 DB）。

    结果进程级缓存：首次探测后不再重复（避免每连接都试一遍）。
    """
    global _vec_available
    if _vec_available is not None:
        return _vec_available
    try:
        import sqlite3

        import sqlite_vec  # type: ignore[import-not-found]

        conn = sqlite3.connect(":memory:")
        conn.enable_load_extension(True)
        conn.load_extension(sqlite_vec.loadable_path())
        conn.execute("SELECT vec_version()")
        conn.close()
        _vec_available = True
        log.info("sqlite-vec 可用，向量检索走 vec0 虚拟表（KNN）")
    except Exception as e:
        _vec_available = False
        log.warning("sqlite-vec 不可用，降级为纯 Python 线性扫描: %s", e)
    return _vec_available


def reset_vec_detection() -> None:
    """重置 sqlite-vec 可用性缓存（测试钩子）。"""
    global _vec_available
    _vec_available = None


# ── VectorStore ─────────────────────────────────────────────


class VectorStore:
    """向量存储：sqlite-vec KNN 或纯 Python 线性扫描降级。

    独立连接到 ``data/vectors.db``（IF_VECTOR_DB_FILE 可配），不侵入主 DB。
    惰性初始化：首次调用任何方法时才建连接 + 建表 + 加载扩展。
    """

    def __init__(self, db_path: str, enabled: bool = True) -> None:
        self._db_path = db_path
        self._enabled = enabled
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._initialized = False
        self._use_vec = False
        self._pool_loop: asyncio.AbstractEventLoop | None = None

    async def _ensure_initialized(self) -> None:
        """惰性初始化：建连接 + 建表 + 加载 sqlite-vec 扩展。"""
        if self._initialized:
            cur_loop = asyncio.get_running_loop()
            if self._pool_loop is not cur_loop:
                await self._rebuild_for_loop(cur_loop)
            return
        async with self._lock:
            if self._initialized:
                return
            os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
            self._conn = await aiosqlite.connect(self._db_path, isolation_level=None)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA synchronous=NORMAL")
            await self._conn.execute("PRAGMA busy_timeout=10000")

            # 探测并加载 sqlite-vec
            self._use_vec = _detect_vec_available()
            if self._use_vec:
                try:
                    await self._conn.enable_load_extension(True)
                    import sqlite_vec  # type: ignore[import-not-found]

                    await self._conn.load_extension(sqlite_vec.loadable_path())
                except Exception as e:
                    log.warning("sqlite-vec 扩展加载失败，降级线性扫描: %s", e)
                    self._use_vec = False

            await self._init_schema()
            self._initialized = True
            try:
                self._pool_loop = asyncio.get_running_loop()
            except RuntimeError:
                self._pool_loop = None

    async def _rebuild_for_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """当前 loop 与连接绑定 loop 不一致：关旧连接、在新 loop 重建。"""
        log.warning("VectorStore loop 漂移（%s → %s），重建连接", self._pool_loop, loop)
        await self.close()
        async with self._lock:
            self._initialized = False
        await self._ensure_initialized()

    async def _init_schema(self) -> None:
        """建表 + 索引 + vec0 虚拟表（若可用）。"""
        assert self._conn is not None
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_vectors (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT UNIQUE NOT NULL,
                embedding BLOB NOT NULL,
                prompt_hash TEXT NOT NULL,
                created_at REAL NOT NULL,
                is_duplicate INTEGER DEFAULT 0,
                duplicate_of TEXT
            )
            """
        )
        await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_tv_task_id ON task_vectors(task_id)")
        await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_tv_prompt_hash ON task_vectors(prompt_hash)")
        await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_tv_is_dup ON task_vectors(is_duplicate)")
        await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_tv_created ON task_vectors(created_at)")

        if self._use_vec:
            # vec0 虚拟表：rowid 与 task_vectors.rowid 对齐
            # embedding float[256] 与 embed.EMBED_DIM 一致
            await self._conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS task_vectors_vec USING vec0(embedding float[{embed.EMBED_DIM}])"
            )
        await self._conn.commit()

    # ── 写 ────────────────────────────────────────────

    async def upsert(
        self,
        task_id: str,
        prompt: str,
        created_at: float | None = None,
        check_duplicate: bool = True,
        duplicate_threshold: float = 0.95,
    ) -> dict[str, Any]:
        """入库时计算 embedding 并写入向量表。

        Args:
            task_id: 任务 ID
            prompt: 任务 prompt
            created_at: 创建时间戳（None=now）
            check_duplicate: 是否查重并标记
            duplicate_threshold: 查重相似度阈值（默认 0.95）

        Returns:
            {"task_id", "is_duplicate", "duplicate_of", "similarity"}
        """
        if not self._enabled:
            return {"task_id": task_id, "is_duplicate": False, "duplicate_of": None, "similarity": 0.0}

        import time

        if created_at is None:
            created_at = time.time()

        await self._ensure_initialized()
        assert self._conn is not None

        embedding = embed.compute_embedding(prompt)
        prompt_hash = embed.compute_prompt_hash(prompt)

        # 查重（先查再写，避免查到自己）
        is_duplicate = False
        duplicate_of: str | None = None
        similarity = 0.0

        if check_duplicate:
            dup = await self.find_duplicate(embedding, duplicate_threshold, exclude_task_id=task_id)
            if dup:
                is_duplicate = True
                duplicate_of = dup["task_id"]
                similarity = dup["similarity"]

        # upsert task_vectors
        await self._conn.execute(
            "INSERT INTO task_vectors (task_id, embedding, prompt_hash, created_at, is_duplicate, duplicate_of)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(task_id) DO UPDATE SET"
            " embedding=excluded.embedding,"
            " prompt_hash=excluded.prompt_hash,"
            " created_at=excluded.created_at,"
            " is_duplicate=excluded.is_duplicate,"
            " duplicate_of=excluded.duplicate_of",
            (task_id, embedding, prompt_hash, created_at, int(is_duplicate), duplicate_of),
        )

        # 同步 vec0 虚拟表（若可用）
        if self._use_vec:
            # 取 task_vectors.rowid（AUTOINCREMENT 主键）
            cur = await self._conn.execute("SELECT rowid FROM task_vectors WHERE task_id=?", (task_id,))
            row = await cur.fetchone()
            if row:
                rid = row["rowid"]
                # vec0 不支持 ON CONFLICT，先删后插
                await self._conn.execute("DELETE FROM task_vectors_vec WHERE rowid=?", (rid,))
                await self._conn.execute(
                    "INSERT INTO task_vectors_vec (rowid, embedding) VALUES (?, ?)",
                    (rid, embedding),
                )

        await self._conn.commit()

        return {
            "task_id": task_id,
            "is_duplicate": is_duplicate,
            "duplicate_of": duplicate_of,
            "similarity": similarity,
        }

    async def mark_duplicate(self, task_id: str, duplicate_of: str) -> None:
        """显式标记 task_id 为 duplicate_of 的重复项。"""
        if not self._enabled:
            return
        await self._ensure_initialized()
        assert self._conn is not None
        await self._conn.execute(
            "UPDATE task_vectors SET is_duplicate=1, duplicate_of=? WHERE task_id=?",
            (duplicate_of, task_id),
        )
        await self._conn.commit()

    # ── 读 ────────────────────────────────────────────

    async def find_duplicate(
        self,
        embedding: bytes,
        threshold: float = 0.95,
        exclude_task_id: str | None = None,
    ) -> dict[str, Any] | None:
        """查找相似度 >= threshold 的已存在向量（用于入库前查重）。

        优先返回非重复项（is_duplicate=0）作为 duplicate_of，让重复链指向
        规范的「原始」任务而非其他重复项，避免 duplicate_of 链形成 A→B→C。

        Returns:
            {"task_id", "similarity", "prompt_hash"} 或 None
        """
        if not self._enabled:
            return None
        await self._ensure_initialized()
        assert self._conn is not None

        if self._use_vec:
            # KNN: 取 top 10（过滤排除项 + 优先非重复项后留余量）
            cur = await self._conn.execute(
                "SELECT v.rowid, v.distance, t.task_id, t.prompt_hash, t.is_duplicate"
                " FROM task_vectors_vec v"
                " JOIN task_vectors t ON t.rowid = v.rowid"
                " WHERE v.embedding MATCH ? AND v.k = ?"
                " ORDER BY v.distance",
                (embedding, 10),
            )
            rows = await cur.fetchall()
            # 优先非重复项（让 duplicate_of 指向规范的原始任务）
            candidates = [
                {
                    "task_id": r["task_id"],
                    "similarity": embed.l2_distance_to_similarity(r["distance"]),
                    "prompt_hash": r["prompt_hash"],
                    "is_duplicate": bool(r["is_duplicate"]),
                }
                for r in rows
                if not exclude_task_id or r["task_id"] != exclude_task_id
            ]
            above = [c for c in candidates if c["similarity"] >= threshold]
            if not above:
                return None
            # 优先非重复项；全为重复项时退而取首个
            for c in above:
                if not c["is_duplicate"]:
                    return c
            return above[0]

        # 降级：线性扫描
        cur = await self._conn.execute(
            "SELECT task_id, embedding, prompt_hash, is_duplicate FROM task_vectors"
        )
        rows = await cur.fetchall()
        best: dict[str, Any] | None = None
        best_sim = 0.0
        for r in rows:
            if exclude_task_id and r["task_id"] == exclude_task_id:
                continue
            sim = embed.cosine_similarity(r["embedding"], embedding)
            if sim > best_sim:
                best_sim = sim
                best = {
                    "task_id": r["task_id"],
                    "similarity": sim,
                    "prompt_hash": r["prompt_hash"],
                    "is_duplicate": bool(r["is_duplicate"]),
                }
        if best and best_sim >= threshold:
            return best
        return None

    async def similar_search(
        self,
        task_id: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """KNN 检索：返回与 task_id 最相似的 top_k 个任务。

        Args:
            task_id: 查询锚点任务 ID
            top_k: 返回数量上限

        Returns:
            [{"task_id", "similarity", "prompt_hash", "created_at", "is_duplicate"}]
            不含 task_id 自身。空列表表示无数据或任务不存在。
        """
        if not self._enabled:
            return []
        await self._ensure_initialized()
        assert self._conn is not None

        # 取锚点 embedding
        cur = await self._conn.execute(
            "SELECT embedding FROM task_vectors WHERE task_id=?", (task_id,)
        )
        row = await cur.fetchone()
        if not row:
            return []
        anchor = row["embedding"]

        if self._use_vec:
            # 取锚点 rowid 用于排除
            cur = await self._conn.execute(
                "SELECT rowid FROM task_vectors WHERE task_id=?", (task_id,)
            )
            r = await cur.fetchone()
            anchor_rid = r["rowid"] if r else -1

            cur = await self._conn.execute(
                "SELECT v.rowid, v.distance, t.task_id, t.prompt_hash, t.created_at, t.is_duplicate"
                " FROM task_vectors_vec v"
                " JOIN task_vectors t ON t.rowid = v.rowid"
                " WHERE v.embedding MATCH ? AND v.k = ?"
                " ORDER BY v.distance",
                (anchor, top_k + 1),
            )
            rows = await cur.fetchall()
            out: list[dict[str, Any]] = []
            for r in rows:
                if r["rowid"] == anchor_rid:
                    continue
                out.append(
                    {
                        "task_id": r["task_id"],
                        "similarity": embed.l2_distance_to_similarity(r["distance"]),
                        "prompt_hash": r["prompt_hash"],
                        "created_at": r["created_at"],
                        "is_duplicate": bool(r["is_duplicate"]),
                    }
                )
                if len(out) >= top_k:
                    break
            return out

        # 降级：线性扫描
        cur = await self._conn.execute(
            "SELECT task_id, embedding, prompt_hash, created_at, is_duplicate"
            " FROM task_vectors WHERE task_id != ?",
            (task_id,),
        )
        rows = await cur.fetchall()
        scored: list[dict[str, Any]] = []
        for r in rows:
            sim = embed.cosine_similarity(r["embedding"], anchor)
            scored.append(
                {
                    "task_id": r["task_id"],
                    "similarity": sim,
                    "prompt_hash": r["prompt_hash"],
                    "created_at": r["created_at"],
                    "is_duplicate": bool(r["is_duplicate"]),
                }
            )
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    async def list_duplicates(self, limit: int = 100) -> list[dict[str, Any]]:
        """列出所有被标记为重复的任务。"""
        if not self._enabled:
            return []
        await self._ensure_initialized()
        assert self._conn is not None
        cur = await self._conn.execute(
            "SELECT task_id, prompt_hash, created_at, duplicate_of"
            " FROM task_vectors WHERE is_duplicate=1"
            " ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
        return [
            {
                "task_id": r["task_id"],
                "prompt_hash": r["prompt_hash"],
                "created_at": r["created_at"],
                "duplicate_of": r["duplicate_of"],
            }
            for r in rows
        ]

    async def stats(self) -> dict[str, Any]:
        """向量存储统计（供 /v1/gallery/similar/stats 或管理端调用）。"""
        if not self._enabled:
            return {"enabled": False, "total": 0, "duplicates": 0, "backend": "disabled"}
        await self._ensure_initialized()
        assert self._conn is not None
        cur = await self._conn.execute(
            "SELECT COUNT(*) AS total,"
            " SUM(CASE WHEN is_duplicate=1 THEN 1 ELSE 0 END) AS duplicates"
            " FROM task_vectors"
        )
        row = await cur.fetchone()
        return {
            "enabled": True,
            "total": int(row["total"] or 0),
            "duplicates": int(row["duplicates"] or 0),
            "backend": "sqlite-vec" if self._use_vec else "linear-scan",
            "dim": embed.EMBED_DIM,
        }

    async def close(self) -> None:
        """关闭连接。"""
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception:
                pass
        self._conn = None
        self._initialized = False
        self._pool_loop = None


# ── 模块级单例（工厂 + 测试钩子）────────────────────────


def _vector_db_path() -> str:
    """向量 DB 路径（默认 data/vectors.db，可通过 IF_VECTOR_DB_FILE 覆盖）。"""
    return os.getenv("IF_VECTOR_DB_FILE", os.path.join(os.path.dirname(config.DB_FILE or "data/imagefree.db"), "vectors.db"))


def _vector_enabled() -> bool:
    """向量检索开关（IF_VECTOR_SEARCH_ENABLED，缺省 0=关闭）。"""
    val = os.getenv("IF_VECTOR_SEARCH_ENABLED", "0")
    return val.strip().lower() in {"1", "true", "yes", "on"}


_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """获取全局 VectorStore 单例（惰性创建）。

    返回的实例始终可用：``_enabled=False`` 时所有方法短路返回空结果，
    不会建连接/建表，零开销。``IF_VECTOR_SEARCH_ENABLED=1`` 时才真正初始化。
    """
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore(_vector_db_path(), enabled=_vector_enabled())
    return _vector_store


def reset_vector_store() -> None:
    """重置全局 VectorStore 单例（测试钩子）。

    丢弃旧实例（关闭其连接），下次 get_vector_store() 创建新实例，
    读取当前 env（IF_VECTOR_SEARCH_ENABLED / IF_VECTOR_DB_FILE）。
    """
    global _vector_store
    if _vector_store is not None:
        try:
            # 异步 close 在测试 fixture 中由调用方 await，此处仅清引用
            _vector_store._enabled = False  # type: ignore[private-access]
        except Exception:
            pass
    _vector_store = None
    reset_vec_detection()


__all__ = [
    "VectorStore",
    "get_vector_store",
    "reset_vector_store",
    "reset_vec_detection",
]
