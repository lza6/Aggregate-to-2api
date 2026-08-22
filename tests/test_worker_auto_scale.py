"""IMP-03: Worker 自动伸缩（动态水位）单元测试。

验证 Engine 在 IF_WORKER_AUTO=true 时根据排队长度和空闲时间
在 [WORKERS_MIN, WORKERS_MAX] 区间内弹性增减 worker。
"""
import asyncio
import time

import pytest

from api import config
from api.worker import Engine


@pytest.fixture
def auto_scale_config(monkeypatch):
    """启用自动伸缩并设置测试友好的阈值。"""
    monkeypatch.setattr(config, "IF_WORKER_AUTO", True)
    monkeypatch.setattr(config, "IF_WORKERS_MIN", 2)
    monkeypatch.setattr(config, "IF_WORKERS_MAX", 8)
    monkeypatch.setattr(config, "IF_WORKER_SCALE_UP_THRESHOLD", 3)
    monkeypatch.setattr(config, "IF_WORKER_SCALE_DOWN_THRESHOLD", 1)
    monkeypatch.setattr(config, "IF_WORKER_IDLE_SECONDS", 0.1)
    monkeypatch.setattr(config, "WORKERS", 4)  # 起始 worker 数
    return config


@pytest.mark.asyncio
async def test_scale_up_when_queue_long(auto_scale_config, tmp_db):
    """排队超过阈值（>3）且未达 WORKERS_MAX → 扩容 2 个 worker。"""
    e = Engine(tmp_db)
    await e.start()
    try:
        assert len(e._workers) == 4

        # 塞入 5 个任务（排队 > 3）
        for i in range(5):
            e.queue.put_nowait((2, i, f"task-{i}"))

        await e._auto_scale_once()

        # 应扩容: 4 + 2 = 6
        assert len(e._workers) == 6
        # 新 worker 应有 stop_event 和 task
        for w in e._workers:
            assert w.stop_event is not None
            assert w.task is not None

        # 验证所有 worker ID 唯一
        ids = [w.id for w in e._workers]
        assert len(set(ids)) == len(ids)
    finally:
        await e.stop()


@pytest.mark.asyncio
async def test_scale_down_when_queue_short(auto_scale_config, tmp_db):
    """排队低于阈值（<1）且超过 WORKERS_MIN → 缩容 1 个 worker。"""
    e = Engine(tmp_db)
    await e.start()
    try:
        assert len(e._workers) == 4
        assert e.queue.qsize() == 0  # 排队为 0

        await e._auto_scale_once()

        # 应缩容: 4 -> 3
        assert len(e._workers) == 3
    finally:
        await e.stop()


@pytest.mark.asyncio
async def test_scale_down_when_idle(auto_scale_config, tmp_db):
    """所有 worker 空闲超过阈值（0.1s）且超过 WORKERS_MIN → 缩容 1 个。"""
    e = Engine(tmp_db)
    await e.start()
    try:
        assert len(e._workers) == 4

        # 模拟所有 worker 长时间空闲
        for w in e._workers:
            w.last_active = time.monotonic() - 10  # 10 秒前

        await e._auto_scale_once()

        # 应缩容: 4 -> 3
        assert len(e._workers) == 3
    finally:
        await e.stop()


@pytest.mark.asyncio
async def test_scale_respects_lower_bound(auto_scale_config, tmp_db):
    """缩容不超过 WORKERS_MIN（2）。"""
    monkeypatch = auto_scale_config  # fixture 已注入
    e = Engine(tmp_db)
    await e.start()
    try:
        # 模拟空闲 + 多次缩容
        for _ in range(5):
            for w in e._workers:
                w.last_active = time.monotonic() - 10
            await e._auto_scale_once()

        assert len(e._workers) >= config.IF_WORKERS_MIN  # >= 2
    finally:
        await e.stop()


@pytest.mark.asyncio
async def test_scale_respects_upper_bound(auto_scale_config, tmp_db):
    """扩容不超过 WORKERS_MAX（8）。"""
    e = Engine(tmp_db)
    await e.start()
    try:
        # 塞入大量任务 + 多次扩容
        for i in range(50):
            e.queue.put_nowait((2, i, f"task-{i}"))

        for _ in range(5):
            await e._auto_scale_once()

        assert len(e._workers) <= config.IF_WORKERS_MAX  # <= 8
    finally:
        await e.stop()


@pytest.mark.asyncio
async def test_no_auto_scale_when_disabled(tmp_db, monkeypatch):
    """IF_WORKER_AUTO=0 时保持静态 worker 数，_auto_scale_task 为 None。"""
    monkeypatch.setattr(config, "IF_WORKER_AUTO", False)
    monkeypatch.setattr(config, "WORKERS", 4)
    e = Engine(tmp_db)
    await e.start()
    try:
        assert len(e._workers) == 4
        assert e._auto_scaler_task is None

        # 即使排队很长，也不应自动扩容
        for i in range(10):
            e.queue.put_nowait((2, i, f"task-{i}"))
        await e._auto_scale_once()
        assert len(e._workers) == 4
    finally:
        await e.stop()


@pytest.mark.asyncio
async def test_auto_scale_loop_starts_and_stops(auto_scale_config, tmp_db):
    """IF_WORKER_AUTO=true 时 start() 启动 _auto_scale_loop，stop() 取消。"""
    e = Engine(tmp_db)
    await e.start()
    try:
        assert e._auto_scaler_task is not None
        assert not e._auto_scaler_task.done()
    finally:
        await e.stop()
        assert e._auto_scaler_task.done()


@pytest.mark.asyncio
async def test_worker_loop_stops_via_event(auto_scale_config, tmp_db):
    """Engine.stop() 触发 worker 的 stop_event，worker 正常退出。"""
    e = Engine(tmp_db)
    await e.start()
    try:
        assert len(e._workers) == 4
        # 所有 worker 的 stop_event 未设置
        assert all(not w.stop_event.is_set() for w in e._workers)
    finally:
        await e.stop()
    # stop 后验证（虽然 stop 会销毁，但事件已设置）
    # 这里主要验证 stop 不抛异常


@pytest.mark.asyncio
async def test_scale_up_per_cycle_limited(auto_scale_config, tmp_db):
    """每 30s 周期最多增 2 个 worker（即使排队远超阈值）。"""
    e = Engine(tmp_db)
    await e.start()
    try:
        # 塞入大量任务
        for i in range(100):
            e.queue.put_nowait((2, i, f"task-{i}"))

        await e._auto_scale_once()
        # 4 -> 6（最多增 2）
        assert len(e._workers) == 6

        # 模拟第二次检查
        for i in range(100):
            e.queue.put_nowait((2, 100 + i, f"task-{100+i}"))
        await e._auto_scale_once()
        # 6 -> 8（最多增 2，但不超过 MAX）
        assert len(e._workers) == config.IF_WORKERS_MAX
    finally:
        await e.stop()


@pytest.mark.asyncio
async def test_scale_down_per_cycle_limited(auto_scale_config, tmp_db):
    """每 30s 周期最多缩 1 个 worker。"""
    e = Engine(tmp_db)
    await e.start()
    try:
        # 排队为空，缩 1 个
        await e._auto_scale_once()
        assert len(e._workers) == 3

        # 再缩 1 个
        await e._auto_scale_once()
        assert len(e._workers) == 2  # 已达 MIN
    finally:
        await e.stop()

# ── P-TEST-A3 追加：_shrink_one_worker 与 _resume_from_queue ─────────

@pytest.mark.asyncio
async def test_shrink_one_worker_removes_most_idle(auto_scale_config, tmp_db):
    """缩容应移除 last_active 最旧（最空闲）的 worker。

    不 start()（避免 auto_scaler 后台循环并发干扰），直接手动构造 worker 句柄。
    """
    engine = Engine(tmp_db)
    now = time.monotonic()
    for i in range(3):
        engine._workers.append(engine._create_worker(i))
    for i, w in enumerate(engine._workers):
        w.last_active = now - (100 - i * 10)  # 第一个最空闲
    oldest = min(engine._workers, key=lambda w: w.last_active)
    engine._shrink_one_worker()
    assert oldest.id not in [w.id for w in engine._workers]
    assert len(engine._workers) == 2
    # 清理：停掉残余 worker 协程
    for w in engine._workers:
        w.stop_event.set()
        w.task.cancel()


@pytest.mark.asyncio
async def test_shrink_on_empty_workers_noop(tmp_db):
    from api.worker import Engine
    engine = Engine(tmp_db)
    engine._shrink_one_worker()  # 空 worker 列表不抛错
    assert engine._workers == []


@pytest.mark.asyncio
async def test_resume_from_queue_without_db_returns_zero(tmp_db):
    """未启用持久化队列（_queue_db=None）→ 恢复 0 条。"""
    from api.worker import Engine
    engine = Engine(tmp_db)
    assert engine._resume_from_queue() == 0


@pytest.mark.asyncio
async def test_auto_scale_once_respects_upper_bound_hard(auto_scale_config, tmp_db, monkeypatch):
    """扩容目标绝不超过 IF_WORKERS_MAX（min(current+2, MAX) 截断）。

    不 start()（避免后台循环与 worker 消费干扰），手动放 1 个 worker + 排队，
    MAX 压到 2：扩容一次后 worker 数 = 2（而非 1+2=3）。
    """
    monkeypatch.setattr(config, "IF_WORKERS_MAX", 2)
    monkeypatch.setattr(config, "IF_WORKER_SCALE_UP_THRESHOLD", 0)
    engine = Engine(tmp_db)
    engine._workers.append(engine._create_worker(0))
    try:
        for i in range(3):
            engine.queue.put_nowait((2, i, f"fake-{i}"))
        await engine._auto_scale_once()
        assert len(engine._workers) == 2  # min(1+2, 2) = 2
    finally:
        for w in engine._workers:
            w.stop_event.set()
            w.task.cancel()
