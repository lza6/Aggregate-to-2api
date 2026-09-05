"""Turnstile 求解集群 Federation、429 熔断与双缓冲池 E2E 集成测试。"""

import asyncio
import time

import pytest

from api import turnstile_client
from api.solver_guard import SolverGuard
from api.worker.token_pool import TokenPoolManager


class MockEngine:
    def __init__(self):
        self._started = True
        self.queue = asyncio.Queue()


@pytest.mark.asyncio
async def test_solver_federation_least_inflight_and_weights():
    """测试 Solver 集群按权重与 inflight 动态负载均衡调度。"""
    guard = SolverGuard(
        urls=["http://node1:8001", "http://node2:8001"],
        weights={"http://node1:8001": 2, "http://node2:8001": 1},
        rate_limit_cooldown=60.0,
    )

    # 初始状态，node1 权重更大，优先被选
    node = guard.select_node()
    assert node is not None
    assert node.url in ["http://node1:8001", "http://node2:8001"]

    # 给 node1 增加 inflight
    n1 = guard._nodes["http://node1:8001"]
    n1.acquire_inflight()
    n1.acquire_inflight()  # inflight=2, weight=2 -> score=1.0

    # 此时 node2 (inflight=0, weight=1 -> score=0.0) 应当被选中
    selected = guard.select_node()
    assert selected.url == "http://node2:8001"

    n1.release_inflight()
    n1.release_inflight()


@pytest.mark.asyncio
async def test_solver_node_429_circuit_break_and_failover(monkeypatch):
    """测试单个节点 429 时自动触发 60s 熔断，并透明 failover 至健康备用节点。"""
    guard = SolverGuard(
        urls=["http://node-bad:8001", "http://node-good:8001"],
        rate_limit_cooldown=60.0,
    )
    monkeypatch.setattr(turnstile_client, "solver_guard", guard)

    call_history = []

    async def mock_solve_internal(target_node, url, sitekey, timeout, proxy):
        call_history.append(target_node)
        if target_node == "http://node-bad:8001":
            raise turnstile_client.TurnstileRateLimited("429 rate limited")
        return "token-from-good-node"

    monkeypatch.setattr(turnstile_client, "_solve_turnstile", mock_solve_internal)

    token, dur = await turnstile_client.solve_turnstile(url="https://imagefree.net", sitekey="0x4A")
    assert token == "token-from-good-node"
    assert "http://node-bad:8001" in call_history
    assert "http://node-good:8001" in call_history

    # 检查 bad 节点已被 429 熔断
    bad_node = guard._nodes["http://node-bad:8001"]
    assert bad_node.is_rate_limited()
    assert bad_node.circuit_open

    # 再次请求，直接由 good 节点处理，不再访问 bad 节点
    call_history.clear()
    token2, _ = await turnstile_client.solve_turnstile(url="https://imagefree.net", sitekey="0x4A")
    assert token2 == "token-from-good-node"
    assert call_history == ["http://node-good:8001"]


@pytest.mark.asyncio
async def test_token_pool_double_buffering_zero_latency(monkeypatch):
    """测试双缓冲池 Active/Standby 队列原子切换与 0ms 消费。"""
    engine = MockEngine()
    manager = TokenPoolManager(engine)

    solve_count = 0

    async def mock_solve(*args, **kwargs):
        nonlocal solve_count
        solve_count += 1
        return f"mock-tok-{solve_count}", 0.05

    monkeypatch.setattr(turnstile_client, "solve_turnstile", mock_solve)

    # 启动双缓冲池
    await manager.start()
    pool = manager._ensure_pool("direct")

    # 手动填充 Active Buffer 与 Standby Buffer
    await pool.active_q.put(("token-active-1", time.time()))
    await pool.standby_q.put(("token-standby-1", time.time()))

    # 1. 首次获取：从 Active Buffer 0ms 获取
    t0 = time.monotonic()
    t1 = await manager.acquire("direct", timeout=1.0)
    cost1 = time.monotonic() - t0
    assert t1 == "token-active-1"
    assert cost1 < 0.05  # 极速 0ms 获取

    # 2. 第二次获取：Active 为空，触发 Double-Buffer Swap 从 Standby 取得
    t0 = time.monotonic()
    t2 = await manager.acquire("direct", timeout=1.0)
    cost2 = time.monotonic() - t0
    assert t2 == "token-standby-1"
    assert cost2 < 0.05
    assert pool.buffer_swaps_total >= 1

    # 快照校验
    snap = manager.pools_snapshot()["direct"]
    assert "active_size" in snap
    assert "standby_size" in snap
    assert snap["buffer_swaps_total"] >= 1
    assert snap["zero_latency_hits"] == 2

    await manager.stop()
