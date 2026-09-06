"""P1-5: Worker 自适应扩缩容多维评分模块 + 编排逻辑。

升级单维（队列深度）为多维加权评分：
- queue_depth（40%）：当前排队任务数相对容量的占比
- upstream_latency_ewma（30%）：上游时延 EWMA 相对 generate_timeout 的占比
- token_pool_level（20%）：token 池水位相对目标水位的占比
- proxy_health（10%）：代理池健康分（健康代理占比）
- memory_pressure（硬限制）：内存使用率超过阈值直接禁止扩容

决策：
- scale_up：综合分 > UP 阈值 且 workers < max
- scale_down：综合分 < DOWN 阈值 且 持续 IF_WORKER_SCALE_DOWN_HOLD 秒（防抖动）

P0-F4 拆分（v8.3.0）：把 _auto_scale_once / _auto_scale_multi_dim /
_idle_workers_count 的编排逻辑从 Engine 类下沉到本模块，Engine 仅保留
薄委托（_auto_scale_once 签名不变，内部委托 run_auto_scale_once）与
_shrink_one_worker（直接操作 self._workers，被测试直接调用，保留为方法）。
_auto_scale_loop 仍留在 Engine（简单循环 + 异常吞咽）。

向后兼容：IF_WORKER_SCALER_LEGACY=1 走旧单维逻辑（_legacy_scale_once）。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from .. import config
from ..worker_health import worker_health

log = logging.getLogger("engine.scaler")


@dataclass
class ScaleMetrics:
    """扩缩容决策的多维指标（各值已归一化到 [0,1] 或绝对计数）。"""

    queue_depth: float = 0.0  # 排队数 / 队列容量（0~1，越高越需要扩容）
    upstream_latency_ewma: float = 0.0  # 上游时延 EWMA / generate_timeout（0~1，越高越慢）
    token_pool_level: float = 0.0  # 当前 token 数 / 目标水位（0~1，越低越紧缺）
    proxy_health: float = 1.0  # 健康代理占比（0~1，越低越差）
    memory_pressure: float = 0.0  # 内存使用率（0~1，>0.9 禁止扩容）


@dataclass
class _ScaleState:
    """扩缩容防抖动状态（模块级单例，engine 调用方持有）。"""

    low_score_since: float = 0.0  # 综合分低于阈值的时刻（monotonic）


def compute_score(m: ScaleMetrics) -> float:
    """多维加权综合分（0~1，越高越需要扩容）。

    权重：queue 40% + latency 30% + token 20% + proxy 10%。
    memory_pressure 作为硬限制：>0.9 时综合分强制归 0（禁止扩容，防 OOM）。
    """
    # 硬限制：内存压力大时禁止扩容（512MB 容器 OOM 风险）
    if m.memory_pressure > 0.9:
        return 0.0
    # token 水位低 → 需要扩容（更多 worker 等待 token，但 token 缺乏时扩容也无益，反向下调）
    # 此处 token_pool_level 越低（越接近 0）表示越缺 token，但缺 token 时扩容无益，故用 (1-level)
    token_factor = 1.0 - m.token_pool_level  # 水位低 → factor 高 → 倾向不扩容（避免无 token 空转）
    score = (
        0.4 * m.queue_depth
        + 0.3 * m.upstream_latency_ewma
        + 0.2 * (1.0 - token_factor)  # 水位充足才倾向扩容
        + 0.1 * m.proxy_health
    )
    return max(0.0, min(1.0, score))


def should_scale_up(m: ScaleMetrics, current_workers: int) -> bool:
    """是否应扩容：综合分 > UP 阈值 且 未达 workers_max。

    UP 阈值取 IF_WORKER_SCALE_UP_THRESHOLD 相对容量的占比（兼容旧 config 语义）。
    """
    score = compute_score(m)
    # 综合分 > 0.6 视为高负载（可配 IF_WORKER_SCALE_UP_SCORE=0.6，此处硬编码 0.6）
    up_threshold = 0.6
    return score > up_threshold and current_workers < config.IF_WORKERS_MAX


def should_scale_down(m: ScaleMetrics, current_workers: int, state: _ScaleState, now: float) -> bool:
    """是否应缩容：综合分 < DOWN 阈值 且 持续 IF_WORKER_SCALE_DOWN_HOLD 秒。

    防抖动：低分必须持续 hold 秒才触发缩容，避免瞬时低负载误缩。
    """
    score = compute_score(m)
    down_threshold = 0.3
    if current_workers <= config.IF_WORKERS_MIN:
        return False
    if score < down_threshold:
        if state.low_score_since == 0.0:
            state.low_score_since = now
        hold = getattr(config, "IF_WORKER_SCALE_DOWN_HOLD", 30)
        return (now - state.low_score_since) >= hold
    # 分数回升，重置计时
    state.low_score_since = 0.0
    return False


def collect_metrics(
    queue_count: int,
    queue_capacity: int,
    upstream_latency_ewma_ms: float,
    token_pool_size: int,
    token_target: int,
    proxy_health_ratio: float,
    memory_pressure: float,
) -> ScaleMetrics:
    """从 engine 各子系统收集指标，归一化为 ScaleMetrics。"""
    qdepth = (queue_count / queue_capacity) if queue_capacity > 0 else 0.0
    latency = (upstream_latency_ewma_ms / (config.GENERATE_TIMEOUT * 1000)) if config.GENERATE_TIMEOUT > 0 else 0.0
    token_level = (token_pool_size / token_target) if token_target > 0 else 1.0
    return ScaleMetrics(
        queue_depth=min(1.0, qdepth),
        upstream_latency_ewma=min(1.0, latency),
        token_pool_level=min(1.0, token_level),
        proxy_health=max(0.0, min(1.0, proxy_health_ratio)),
        memory_pressure=max(0.0, min(1.0, memory_pressure)),
    )


# ── P0-F4: 编排逻辑（从 Engine 类下沉）──────────────────────────

def _idle_workers_count(engine: Any) -> int:
    """统计空闲超过 IF_WORKER_IDLE_SECONDS 的 worker 数。"""
    now = time.monotonic()
    idle_threshold = config.IF_WORKER_IDLE_SECONDS
    return sum(1 for w in engine._workers if now - w.last_active > idle_threshold)


async def _legacy_scale_once(engine: Any) -> None:
    """旧单维逻辑（IF_WORKER_SCALER_LEGACY=1 时使用）。

    保留以兼容 v7.7.17 之前的扩缩容行为：
    - 扩容：排队 > 阈值 且 未达上限 → 增 2 个（最多增 2 / 30s）
    - 缩容：排队 < 阈值，或至少 1 个 worker 空闲超阈值 → 缩 1 个
    """
    qsize = engine.queue.qsize()
    current = len(engine._workers)

    # 扩容：排队 > 阈值 且 未达上限 → 增 2 个（最多增 2 / 30s）
    if qsize > config.IF_WORKER_SCALE_UP_THRESHOLD and current < config.IF_WORKERS_MAX:
        target = min(current + 2, config.IF_WORKERS_MAX)
        added = target - current
        for _ in range(added):
            next_idx = max((w.id for w in engine._workers), default=-1) + 1
            engine._workers.append(engine._create_worker(next_idx))
        log.info(
            "自动扩容: %d → %d（排队 %d > %d）",
            current, target, qsize, config.IF_WORKER_SCALE_UP_THRESHOLD,
        )
        return

    # 缩容：已过最小值才考虑（未过最小值无需缩容）
    if current <= config.IF_WORKERS_MIN:
        return

    # 缩容触发条件：排队 < 阈值，或至少 1 个 worker 空闲超阈值
    idle_count = _idle_workers_count(engine)
    if qsize < config.IF_WORKER_SCALE_DOWN_THRESHOLD:
        reason = f"排队 {qsize} < {config.IF_WORKER_SCALE_DOWN_THRESHOLD}"
    elif idle_count >= 1:
        reason = f"{idle_count} 个 worker 空闲超过 {config.IF_WORKER_IDLE_SECONDS}s"
    else:
        return  # 既不扩容也不满足缩容条件 → 本轮不动作

    engine._shrink_one_worker()
    worker_health.register([w.id for w in engine._workers])
    log.info("自动缩容: %d → %d（%s）", current, len(engine._workers), reason)


async def _auto_scale_multi_dim(engine: Any) -> None:
    """v8.0 P1-5: 多维评分扩缩容。

    收集 queue/latency/token/proxy/memory 指标，调 scaler 决策。
    memory_pressure 通过 psutil 获取（可选，无 psutil 时默认 0）。
    """
    qsize = engine.queue.count()
    current = len(engine._workers)
    capacity = engine.queue.capacity()

    # 上游时延 EWMA：从 solver/adaptive_router 无直接值，用 token_pool 的等待超时计数近似
    upstream_latency_ewma_ms = float(getattr(engine.token_pool_manager, "wait_timeout_total", 0)) * 1000.0

    # token 池水位
    direct_pool = engine.token_pool_manager.pools.get("direct")
    token_size = direct_pool.size() if direct_pool else 0
    token_target = config.TOKEN_POOL_SIZE

    # 代理池健康
    try:
        proxy_health_ratio = engine._proxy_pool.health_ratio() if hasattr(engine._proxy_pool, "health_ratio") else 1.0
    except Exception:
        proxy_health_ratio = 1.0

    # 内存压力（可选 psutil）
    memory_pressure = 0.0
    try:
        import psutil

        memory_pressure = psutil.virtual_memory().percent / 100.0
    except Exception:
        memory_pressure = 0.0

    metrics = collect_metrics(
        queue_count=qsize,
        queue_capacity=capacity,
        upstream_latency_ewma_ms=upstream_latency_ewma_ms,
        token_pool_size=token_size,
        token_target=token_target,
        proxy_health_ratio=proxy_health_ratio,
        memory_pressure=memory_pressure,
    )

    if should_scale_up(metrics, current):
        target = min(current + 2, config.IF_WORKERS_MAX)
        added = target - current
        for _ in range(added):
            next_idx = max((w.id for w in engine._workers), default=-1) + 1
            engine._workers.append(engine._create_worker(next_idx))
        log.info(
            "自动扩容(多维): %d → %d（score=%.2f, q=%d/%d）",
            current, target, compute_score(metrics), qsize, capacity,
        )
        return

    now = time.monotonic()
    if should_scale_down(metrics, current, engine._scale_state, now):
        engine._shrink_one_worker()
        worker_health.register([w.id for w in engine._workers])
        log.info(
            "自动缩容(多维): %d → %d（score=%.2f, 持续 %ss）",
            current, len(engine._workers), compute_score(metrics), config.IF_WORKER_SCALE_DOWN_HOLD,
        )


async def run_auto_scale_once(engine: Any) -> None:
    """单次伸缩检查入口（Engine._auto_scale_once 委托此函数）。

    - 默认走多维评分路径（_auto_scale_multi_dim）
    - IF_WORKER_SCALER_LEGACY=1 走旧单维路径（_legacy_scale_once）
    """
    if not getattr(config, "IF_WORKER_SCALER_LEGACY", False):
        await _auto_scale_multi_dim(engine)
        return
    await _legacy_scale_once(engine)


__all__ = [
    "ScaleMetrics",
    "compute_score",
    "should_scale_up",
    "should_scale_down",
    "collect_metrics",
    "run_auto_scale_once",
]
