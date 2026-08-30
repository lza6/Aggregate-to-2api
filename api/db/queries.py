"""QueueDB 类（已废弃，请使用 QueueStore）+ task_to_public 函数。"""

from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger("db")


class QueueDB:
    """持久化队列 DB（同步实现，**已废弃**）。

    ⚠️ 此实现使用同步 sqlite3，会阻塞事件循环。
    请使用 `api.db.queue_store.QueueStore`（异步 aiosqlite）替代。

    保留仅为兼容已有引用，**不要在新代码中使用**。
    """

    def __init__(self, path: str):
        import sqlite3

        self._conn = sqlite3.connect(path, check_same_thread=False)
        # 极限性能调优参数（v5.2）：与主库一致的写读无锁并发 + 内存缓存
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._conn.execute("PRAGMA cache_size=-64000")  # 64MB
        self._conn.execute("PRAGMA mmap_size=268435456")  # 256MB
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS task_queue (
                    id          TEXT PRIMARY KEY,
                    priority    INT DEFAULT 2,
                    seq         INT,
                    created_at  REAL,
                    status      TEXT DEFAULT 'pending'
                );
                CREATE INDEX IF NOT EXISTS idx_queue_status ON task_queue(status);
                CREATE INDEX IF NOT EXISTS idx_queue_priority ON task_queue(priority, seq);
            """)
            self._conn.commit()

    def enqueue(self, task_id: str, priority: int, seq: int) -> None:
        """写入待消费队列。"""
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO task_queue (id, priority, seq, created_at, status)"
                " VALUES (?, ?, ?, ?, 'pending')",
                (task_id, priority, seq, time.time()),
            )
            self._conn.commit()

    def mark_processing(self, task_id: str) -> None:
        """标记为处理中。"""
        with self._lock:
            self._conn.execute("UPDATE task_queue SET status='processing' WHERE id=?", (task_id,))
            self._conn.commit()

    def mark_completed(self, task_id: str) -> None:
        """标记为已完成。"""
        with self._lock:
            self._conn.execute("UPDATE task_queue SET status='completed' WHERE id=?", (task_id,))
            self._conn.commit()

    def list_pending(self) -> list[tuple[int, int, str]]:
        """返回所有 pending 任务，按 priority/seq 升序。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT priority, seq, id FROM task_queue" " WHERE status='pending' ORDER BY priority, seq"
            ).fetchall()
            return [(r[0], r[1], r[2]) for r in rows]

    def cleanup(self, retention_days: int = 7) -> dict:
        """清理超期 completed/processing 记录，返回删除数。"""
        cutoff = time.time() - retention_days * 86400
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM task_queue WHERE status IN ('completed','processing') AND created_at < ?",
                (cutoff,),
            )
            self._conn.commit()
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            return {"deleted": cur.rowcount}

    def close(self) -> None:
        self._conn.close()


def task_to_public(t: dict) -> dict:
    """数据库行 → API 响应结构。"""
    from ..geo_ip import guess_country

    b64 = t.get("image_base64")
    if b64 and isinstance(b64, str) and b64.startswith("file://"):
        path = b64[7:]
        try:
            with open(path, encoding="utf-8") as f:
                b64 = f.read()
            if len(b64) > 10 * 1024 * 1024:
                log.warning("base64 文件超过 10MB 限制，跳过 task_to_public: %s", path)
                b64 = None
        except OSError:
            b64 = None

    ip = t.get("client_ip") or ""
    loc_info = guess_country(ip) if ip else None
    loc_str = f"{loc_info['emoji']} {loc_info['desc']}" if loc_info else "—"
    # 私网/回环/链路本地（LAN）：不回传原始 IP，防内网拓扑泄露被恶意者利用
    is_internal = bool(loc_info and loc_info.get("code") in ("LAN",))
    public_ip = "" if is_internal else (t.get("client_ip") or "")

    # 阶段耗时拆解（从 error / slow / duration 提炼）
    dur = t.get("duration_sec")
    timings = {}
    if dur is not None:
        timings["total_sec"] = round(dur, 2)

    return {
        "id": t["id"],
        "status": t["status"],
        "image_url": t["image_url"],
        "image_base64": b64,
        "image_mime": t.get("image_mime"),
        "error": t["error"],
        "created_at": t["created_at"],
        "duration_sec": t["duration_sec"],
        "type": t.get("type", "txt"),
        "model": t.get("model", "default"),
        "prompt": t.get("prompt"),
        "aspect_ratio": t.get("aspect_ratio"),
        "client_ip": public_ip or None,
        "client_location": loc_str,
        "user_agent": t.get("user_agent"),
        "timings": timings,
    }
