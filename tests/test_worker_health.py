"""worker 心跳/卡死巡检测试（v3.1.0 S-7 / T-4）。

用注入时钟（now_fn）测，不真 sleep。覆盖：心跳更新、stale 判定、恢复解除、快照。
"""

import pytest

from api.worker_health import WorkerHealthMonitor


@pytest.fixture
def clock():
    """可控单调时钟。"""
    state = {"now": 1000.0}
    return state


def _mon(clock):
    return WorkerHealthMonitor(stale_seconds=180.0, now_fn=lambda: clock["now"])


class TestHeartbeat:
    def test_initial_all_alive(self, clock):
        m = _mon(clock)
        m.register([0, 1])
        snap = m.snapshot()
        assert len(snap) == 2
        assert all(w["alive"] for w in snap)

    def test_heartbeat_updates(self, clock):
        m = _mon(clock)
        m.register([0])
        clock["now"] += 10
        m.beat(0)
        snap = m.snapshot()
        assert snap[0]["last_active_ago_seconds"] == pytest.approx(0.0)


class TestStale:
    def test_stale_detected(self, clock):
        m = _mon(clock)
        m.register([0, 1])
        clock["now"] += 200  # 超过 180s
        m.sweep()
        by_id = {w["id"]: w for w in m.snapshot()}
        assert by_id[0]["alive"] is False
        assert by_id[0]["stale"] is True
        assert by_id[1]["alive"] is False  # 都没心跳都 stale

    def test_recover_after_beat(self, clock):
        m = _mon(clock)
        m.register([0])
        clock["now"] += 200
        m.sweep()
        assert m.snapshot()[0]["stale"] is True
        m.beat(0)  # 恢复心跳
        assert m.snapshot()[0]["stale"] is False

    def test_sweep_only_marks_not_beats(self, clock):
        """sweep 不应刷新 last_active（只巡检不续命）。"""
        m = _mon(clock)
        m.register([0])
        before = m.snapshot()[0]["last_active_monotonic"]
        clock["now"] += 50
        m.sweep()
        after = m.snapshot()[0]["last_active_monotonic"]
        assert before == after


class TestProcessedCounter:
    def test_processed_increment(self, clock):
        m = _mon(clock)
        m.register([0])
        m.add_processed(0)
        m.add_processed(0)
        assert m.snapshot()[0]["processed"] == 2

    def test_unknown_worker_beat_ignored(self, clock):
        """未知 worker id 的 beat 不崩溃、不新建条目。"""
        m = _mon(clock)
        m.register([0])
        m.beat(99)
        assert len(m.snapshot()) == 1

    def test_summary_for_diagnostics(self, clock):
        m = _mon(clock)
        m.register([0, 1, 2])
        clock["now"] += 300
        m.sweep()
        s = m.summary()
        assert s["total"] == 3
        assert s["alive"] == 0
        assert s["stale_ids"] == [0, 1, 2]
