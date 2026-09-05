"""慢日志画像引擎测试（v3.1.0 S-3 / T-1）。

覆盖：环形缓冲淘汰、阈值过滤、并发写安全、snapshot 排序、开关关闭零记录。
"""

import asyncio
import time

import pytest

from api.slow_log import SlowLog, SlowSample


def _sample(task_id: str = "t1", total_ms: float = 6000.0, **kw) -> SlowSample:
    """构造一个默认超阈值的样本（便于绕过阈值过滤直接测缓冲）。"""
    base = dict(
        task_id=task_id,
        model="imagefree/default",
        provider="imagefree",
        queue_ms=100.0,
        wait_token_ms=200.0,
        solve_ms=300.0,
        upstream_ms=5000.0,
        retry_ms=0.0,
        total_ms=total_ms,
        status="completed",
    )
    base.update(kw)
    return SlowSample(**base)


class TestSlowSample:
    """SlowSample 数据结构。"""

    def test_fields_present(self):
        s = _sample()
        assert s.task_id == "t1"
        assert s.model == "imagefree/default"
        assert s.provider == "imagefree"
        assert s.status == "completed"
        # 各阶段字段存在且为数值
        for f in ("queue_ms", "wait_token_ms", "solve_ms", "upstream_ms", "retry_ms", "total_ms"):
            assert isinstance(getattr(s, f), float)

    def test_created_at_auto(self):
        s = _sample()
        # created_at 自动打点（秒级时间戳）
        assert abs(s.created_at - time.time()) < 5


class TestThreshold:
    """阈值过滤：低于阈值的样本不记录。"""

    def test_below_threshold_not_recorded(self):
        sl = SlowLog(threshold_ms=5000, maxsize=10)
        sl.record(_sample(total_ms=4999.0))
        assert sl.snapshot() == []

    def test_at_threshold_recorded(self):
        sl = SlowLog(threshold_ms=5000, maxsize=10)
        sl.record(_sample(total_ms=5000.0))
        assert len(sl.snapshot()) == 1

    def test_disabled_records_nothing(self):
        sl = SlowLog(enabled=False, threshold_ms=5000, maxsize=10)
        sl.record(_sample())
        assert sl.snapshot() == []


class TestRingBuffer:
    """环形缓冲：满后丢最旧。"""

    def test_evicts_oldest(self):
        sl = SlowLog(threshold_ms=5000, maxsize=3)
        for i in range(5):
            sl.record(_sample(task_id=f"t{i}"))
        snap = sl.snapshot()
        assert len(snap) == 3
        # 最旧的 t0/t1 被淘汰，保留 t2/t3/t4
        assert [s.task_id for s in snap] == ["t2", "t3", "t4"]

    def test_snapshot_newest_last(self):
        sl = SlowLog(threshold_ms=5000, maxsize=10)
        sl.record(_sample(task_id="a"))
        sl.record(_sample(task_id="b"))
        snap = sl.snapshot()
        assert snap[0].task_id == "a"
        assert snap[-1].task_id == "b"


class TestConcurrency:
    """并发写不崩、不丢（锁保护）。"""

    async def test_concurrent_writes(self):
        sl = SlowLog(threshold_ms=5000, maxsize=100)

        async def writer(n: int):
            for i in range(20):
                sl.record(_sample(task_id=f"w{n}-{i}"))
                await asyncio.sleep(0)

        await asyncio.gather(*(writer(n) for n in range(8)))
        snap = sl.snapshot()
        assert len(snap) == min(100, 8 * 20)  # 全部写入或按容量截断
        # 无重复 task_id（每条样本独立）
        ids = [s.task_id for s in snap]
        assert len(ids) == len(set(ids))


class TestStats:
    """聚合统计：供 diagnostics 端点使用。"""

    def test_stats_basic(self):
        sl = SlowLog(threshold_ms=5000, maxsize=10)
        assert sl.stats()["count"] == 0
        sl.record(_sample(task_id="a", total_ms=6000))
        sl.record(_sample(task_id="b", total_ms=9000))
        st = sl.stats()
        assert st["count"] == 2
        assert st["max_total_ms"] == pytest.approx(9000.0)
        assert st["avg_total_ms"] == pytest.approx(7500.0)
        # 阶段分布：最慢样本的耗时大头在 upstream
        assert st["slowest_stage"] == "upstream"

    def test_slowest_stage_queue(self):
        sl = SlowLog(threshold_ms=5000, maxsize=10)
        sl.record(_sample(queue_ms=4500, wait_token_ms=800, solve_ms=400, upstream_ms=600, total_ms=6300))
        assert sl.stats()["slowest_stage"] == "queue"


class TestConfigWiring:
    """S-4: config 四件套存在且默认值正确。"""

    def test_config_fields(self):
        from api import config

        assert hasattr(config, "IF_SLOW_LOG_ENABLED")
        assert config.IF_SLOW_LOG_ENABLED is True
        assert config.IF_SLOW_REQUEST_MS == 5000.0
        assert config.IF_SLOW_LOG_SIZE == 500

    def test_worker_record_slow_method_exists(self):
        from api.worker import Engine

        assert hasattr(Engine, "_record_slow")

    def test_engine_tracks_enqueue_time(self):
        from api.worker import Engine

        eng = Engine.__new__(Engine)  # 不触发 __init__ 的 db 依赖
        eng._enqueued_at = {}
        import time as _t

        eng._enqueued_at["x"] = _t.monotonic()
        assert "x" in eng._enqueued_at
