"""P1-4: 代理池健康评分（EWMA 成功率）测试。

覆盖：
- 初值 1.0
- 成功 EWMA 上调（0.7*old + 0.3*1）
- 失败 EWMA 下调（0.7*old + 0.3*0）
- 健康分低的候选降级到池底（acquire 优先选健康分高的）
- 连续失败后 health_score 单调下降但 > 0（不立即归零，给恢复机会）
"""

from __future__ import annotations

import pytest

from api.proxy_pool import ProxyEntry, ProxyPool


@pytest.mark.asyncio
async def test_health_score_initial_value():
    e = ProxyEntry("http://1.2.3.4:8080", source="free")
    assert e.health_score == 1.0


@pytest.mark.asyncio
async def test_health_score_success_ewma_up():
    pool = ProxyPool()
    pool.entries = [ProxyEntry("http://1.2.3.4:8080", source="free")]
    await pool.mark_success("http://1.2.3.4:8080")
    # 0.7*1.0 + 0.3*1.0 = 1.0
    assert abs(pool.entries[0].health_score - 1.0) < 1e-9


@pytest.mark.asyncio
async def test_health_score_failure_ewma_down():
    pool = ProxyPool()
    pool.entries = [ProxyEntry("http://1.2.3.4:8080", source="free")]
    await pool.mark_failure("http://1.2.3.4:8080", rate_limited=True)
    # 0.7*1.0 + 0.3*0.0 = 0.7
    assert abs(pool.entries[0].health_score - 0.7) < 1e-9


@pytest.mark.asyncio
async def test_health_score_monotonic_decrease_on_failures():
    pool = ProxyPool()
    pool.entries = [ProxyEntry("http://1.2.3.4:8080", source="free")]
    prev = pool.entries[0].health_score
    for _ in range(5):
        await pool.mark_failure("http://1.2.3.4:8080", rate_limited=False)
        assert pool.entries[0].health_score < prev
        prev = pool.entries[0].health_score
    # 多次失败后健康分很低但 > 0
    assert 0 < pool.entries[0].health_score < 0.2


@pytest.mark.asyncio
async def test_acquire_prefers_healthy_proxy():
    """两个都可用、都未用过时，优先选健康分高的。"""
    pool = ProxyPool()
    e1 = ProxyEntry("http://1.1.1.1:8080", source="free")
    e2 = ProxyEntry("http://2.2.2.2:8080", source="free")
    e1.health_score = 0.3  # 降级
    e2.health_score = 0.9  # 健康
    pool.entries = [e1, e2]
    # 都未用过 → 应选 e2（健康分高）
    picked = await pool.acquire(force_rotate=False)
    assert picked == "http://2.2.2.2:8080"


@pytest.mark.asyncio
async def test_trace_result_updates_health_score():
    """apply_trace_result 反哺健康评分。"""
    pool = ProxyPool()
    pool.entries = [ProxyEntry("http://1.2.3.4:8080", source="free")]
    # real_exit=True → 成功 → EWMA 上调
    await pool.apply_trace_result("http://1.2.3.4:8080", {"exit_ip": "9.9.9.9", "real_exit": True})
    assert abs(pool.entries[0].health_score - 1.0) < 1e-9
    # real_exit=False → 失败 → EWMA 下调
    await pool.apply_trace_result("http://1.2.3.4:8080", {"exit_ip": "1.2.3.4", "real_exit": False})
    assert abs(pool.entries[0].health_score - 0.7) < 1e-9


@pytest.mark.asyncio
async def test_snapshot_includes_health_score():
    pool = ProxyPool()
    pool.entries = [ProxyEntry("http://1.2.3.4:8080", source="free")]
    snap = pool.entries[0].snapshot()
    assert "health_score" in snap
