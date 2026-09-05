"""P1-5: Worker 自适应扩缩容多维评分单元测试。"""

from __future__ import annotations

import time

from api import config
from api.worker.scaler import (
    ScaleMetrics,
    _ScaleState,
    collect_metrics,
    compute_score,
    should_scale_down,
    should_scale_up,
)


def test_compute_score_high_queue_load():
    """高队列负载 → 高分。"""
    m = ScaleMetrics(queue_depth=0.9, upstream_latency_ewma=0.5, token_pool_level=1.0, proxy_health=1.0)
    score = compute_score(m)
    assert score > 0.5, f"高负载应得高分, got {score}"


def test_compute_score_memory_pressure_blocks():
    """内存压力 >0.9 → 综合分强制 0（禁止扩容）。"""
    m = ScaleMetrics(queue_depth=0.9, upstream_latency_ewma=0.9, token_pool_level=1.0, proxy_health=1.0, memory_pressure=0.95)
    assert compute_score(m) == 0.0


def test_compute_score_token_low_reduces_score():
    """token 水位低 → 扩容无益，分数下调。"""
    high_token = ScaleMetrics(queue_depth=0.5, token_pool_level=1.0)
    low_token = ScaleMetrics(queue_depth=0.5, token_pool_level=0.1)
    assert compute_score(low_token) < compute_score(high_token)


def test_should_scale_up_high_score_under_max():
    """高负载 + 未达上限 → 应扩容。"""
    m = ScaleMetrics(queue_depth=0.9, upstream_latency_ewma=0.8, token_pool_level=1.0, proxy_health=1.0)
    assert should_scale_up(m, current_workers=4) is True


def test_should_scale_up_at_max_no_scale():
    """已达 workers_max → 不扩容。"""
    m = ScaleMetrics(queue_depth=0.99, upstream_latency_ewma=0.99, token_pool_level=1.0, proxy_health=1.0)
    assert should_scale_up(m, current_workers=config.IF_WORKERS_MAX) is False


def test_should_scale_down_low_score_after_hold():
    """低负载持续 hold 秒 → 缩容。"""
    m = ScaleMetrics(queue_depth=0.0, upstream_latency_ewma=0.0, token_pool_level=1.0, proxy_health=0.0)
    state = _ScaleState()
    now = time.monotonic()
    # 第一次低分，记录起始
    assert should_scale_down(m, current_workers=10, state=state, now=now) is False
    # 持续 hold 秒后
    later = now + config.IF_WORKER_SCALE_DOWN_HOLD + 1
    assert should_scale_down(m, current_workers=10, state=state, now=later) is True


def test_should_scale_down_reset_on_score_recover():
    """分数回升 → 重置计时，不缩容。"""
    low = ScaleMetrics(queue_depth=0.0)
    high = ScaleMetrics(queue_depth=0.9, upstream_latency_ewma=0.8, token_pool_level=1.0, proxy_health=1.0)
    state = _ScaleState()
    now = time.monotonic()
    should_scale_down(low, current_workers=10, state=state, now=now)
    # 分数回升
    assert should_scale_down(high, current_workers=10, state=state, now=now + 100) is False
    # low_score_since 应被重置
    assert state.low_score_since == 0.0


def test_should_scale_down_at_min_no_scale():
    """已达 workers_min → 不缩容。"""
    m = ScaleMetrics(queue_depth=0.0)
    state = _ScaleState()
    assert should_scale_down(m, current_workers=config.IF_WORKERS_MIN, state=state, now=time.monotonic()) is False


def test_collect_metrics_normalizes():
    """collect_metrics 归一化各指标到 [0,1]。"""
    m = collect_metrics(
        queue_count=100,
        queue_capacity=200,
        upstream_latency_ewma_ms=15000,
        token_pool_size=3,
        token_target=6,
        proxy_health_ratio=0.5,
        memory_pressure=0.7,
    )
    assert 0.0 <= m.queue_depth <= 1.0
    assert 0.0 <= m.upstream_latency_ewma <= 1.0
    assert 0.0 <= m.token_pool_level <= 1.0
    assert 0.0 <= m.proxy_health <= 1.0
    assert 0.0 <= m.memory_pressure <= 1.0
