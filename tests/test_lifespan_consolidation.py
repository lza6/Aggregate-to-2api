"""tests/test_lifespan_consolidation.py — P1-10 记忆巩固 worker 启停生命周期契约。

覆盖（lifespan 接线已由代码核验：startup 调 start_consolidation_loop、
shutdown 调 stop_consolidation_loop）：
- MEMORY_CONSOLIDATION_ENABLED=True → start_consolidation_loop 创建 _consolidation_task
- False → 不创建（零回归，lifespan 缺省关）
- stop_consolidation_loop 取消任务 → task done（不泄漏 CancelledError）
- _consolidation_loop 被取消时 break（不抛 CancelledError）

付费红线：全程 Mock（临时 DB + monkeypatch 模块常量），无真实调用。
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def store(tmp_path):
    """临时 DB 的 MemoryStore（独立实例，不触碰模块级单例）。"""
    from api.agent.memory import MemoryStore

    return MemoryStore(str(tmp_path / "consolidation.db"))


async def test_start_creates_task_when_enabled(store, monkeypatch):
    """开关开 → start 创建 _consolidation_task；stop 后 task done。"""
    import api.agent.memory as mem_mod

    monkeypatch.setattr(mem_mod, "MEMORY_CONSOLIDATION_ENABLED", True)
    await store.start_consolidation_loop()
    assert store._consolidation_task is not None
    assert not store._consolidation_task.done()
    await store.stop_consolidation_loop()
    assert store._consolidation_task.done()


async def test_start_noop_when_disabled(store, monkeypatch):
    """开关关 → start 不创建任务（lifespan 缺省关零回归）。"""
    import api.agent.memory as mem_mod

    monkeypatch.setattr(mem_mod, "MEMORY_CONSOLIDATION_ENABLED", False)
    await store.start_consolidation_loop()
    assert store._consolidation_task is None


async def test_stop_noop_without_task(store):
    """未启动过就 stop → 不崩。"""
    await store.stop_consolidation_loop()


async def test_consolidation_loop_breaks_on_cancel(store):
    """_consolidation_loop 被取消 → 内部 catch CancelledError 并 break（不泄漏）。"""
    task = asyncio.create_task(store._consolidation_loop())
    await asyncio.sleep(0.05)  # 让循环进入 sleep 等待
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pytest.fail("CancelledError 从 _consolidation_loop 泄漏")
    assert task.done()
