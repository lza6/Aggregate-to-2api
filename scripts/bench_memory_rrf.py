"""记忆 RRF 检索压测基准（v18 P0-2，RT-4 先行验证）。

造 1000 条 mem_atoms（临时独立库，含 FTS 同步），对比 plain 与 rrf 查询 P95 延迟。
用法: python scripts/bench_memory_rrf.py [--count 1000]
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncio  # noqa: E402

_TOPICS = (
    "深色背景 电商主图 视觉策划",
    "产品发布会 PPT 大纲 要点",
    "城市夜景 延时摄影 视频",
    "图像质量 水印 检测",
    "客户 详情页 文案 卖点",
    "记忆 偏好 风格 历史",
)


async def _bench(count: int) -> dict:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["IF_DB_FILE"] = path
    try:
        from api.config import reset_settings

        reset_settings()
        from api.agent.memory import MemoryStore

        store = MemoryStore(db_path=path)
        with store._conn() as conn:
            for i in range(count):
                topic = _TOPICS[i % len(_TOPICS)]
                now = time.time()
                conn.execute(
                    "INSERT INTO mem_atoms(user_key, scene, content, importance, created_at, last_accessed_at, source_ids) "
                    "VALUES (?,?,?,?,?,?,?)",
                    ("default", "image", f"{topic} L1-{i}", 0.3 + (i % 50) / 100, now, now, "1"),
                )
            conn.commit()

        async def _probe():
            plain_ms: list[float] = []
            rrf_ms: list[float] = []
            for _ in range(20):
                t0 = time.perf_counter()
                await store.query("default", "image", layer="L1", limit=10, mode="plain")
                plain_ms.append((time.perf_counter() - t0) * 1000)
                t0 = time.perf_counter()
                await store.query("default", "image", layer="L1", limit=10, mode="rrf")
                rrf_ms.append((time.perf_counter() - t0) * 1000)
            return plain_ms, rrf_ms

        plain_ms_raw, rrf_ms_raw = await _probe()
        return {
            "count": count,
            "plain_p95_ms": round(statistics.quantiles(plain_ms_raw, n=20)[-1], 2),
            "rrf_p95_ms": round(statistics.quantiles(rrf_ms_raw, n=20)[-1], 2),
        }
    finally:
        try:
            Path(path).unlink()
        except OSError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1000)
    args = ap.parse_args()
    rep = asyncio.run(_bench(args.count))
    print(f"[bench] count={rep['count']} plain_p95={rep['plain_p95_ms']}ms rrf_p95={rep['rrf_p95_ms']}ms")
    ok = rep["rrf_p95_ms"] < 50
    print(f"[bench] 结论: {'P95<50ms，RRF 可上（建议保持审批/召回校验）' if ok else 'P95>=50ms，RRF 需优化（索引/限流）或保持纯 SQL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
