"""MAB-EWMA 自适应路由引擎：结合时延、成功率、负载的多臂赌博机路由。

痛点（v3.2+）：上游网络突发抖动 / Turnstile 求解器排队时，静态路由或单一成功率
路由容易把流量继续打入慢节点。本引擎用 Epsilon-Greedy-Decay 探索 + EWMA 指数加权
移动平均时延 + 熔断器，实时加权打分选出当次最优 provider。

算法：Score = (成功率 / log10(EWMA时延)) * 负载惩罚
 - 成功率：Laplace 平滑（避免样本少时震荡）
 - EWMA 时延：alpha=0.2 平滑，失败时惩罚放大 1.5x（快速感知抖动）
 - 负载惩罚：in_flight 越高分越低（先进先出，防把流量灌进忙节点）
 - 熔断：失败率 > 50% 且样本 >= 5 → OPEN 30s；到期 HALF_OPEN 试放一个请求
 - 探索：epsilon 概率随机选（探测可能恢复的 provider，随样本数衰减）

路由决策记录（环形缓冲，内存，最多 1000 条）供前端"路由记录"展示，
让开发者知道自己的请求被哪个 provider 处理、为什么。
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any

_MAX_RECORDS = 1000
_OPEN_COOLDOWN = 30.0       # 熔断时长（秒）
_OPEN_FAIL_RATIO = 0.5      # 触发熔断的失败率阈值
_OPEN_MIN_SAMPLES = 5       # 触发熔断的最少样本数
_LATENCY_FLOOR = 100.0      # 时延下限（平滑 log，防除零/负值）
_INIT_EWMA = 2000.0         # 初始预估时延（2s，冷启动公平）
_ALPHA = 0.2                # EWMA 平滑系数


@dataclass
class ProviderNodeStats:
    """单个 provider 的路由统计。"""
    provider_id: str
    success_count: int = 0
    failure_count: int = 0
    ewma_latency_ms: float = _INIT_EWMA
    in_flight_requests: int = 0
    circuit_state: str = "CLOSED"       # CLOSED | OPEN | HALF_OPEN
    circuit_open_until: float = 0.0
    consecutive_failures: int = 0
    last_result_ts: float = 0.0


@dataclass
class RoutingRecord:
    """一次路由决策（供前端路由记录展示）。"""
    ts: float
    request_id: str
    model: str
    selected_provider: str
    requested_provider: str          # 原始（fallback 后真实处理的 provider 见 selected）
    score: float
    scores: dict[str, float]         # 所有候选的评分快照
    latency_ms: int = 0
    success: bool | None = None      # None=尚未完成（fallback 时请求还在途）
    reason: str = "best_score"


class AdaptiveRouter:
    """多提供商自适应路由引擎（线程安全，供 async 环境调用）。"""

    def __init__(self, alpha: float = _ALPHA, initial_explore_rate: float = 0.10) -> None:
        self.alpha = alpha
        self.base_explore_rate = initial_explore_rate
        self._lock = threading.Lock()
        self.nodes: dict[str, ProviderNodeStats] = {}
        self._records: list[RoutingRecord] = []

    # ── 内部工具 ──
    def _record(self, rec: RoutingRecord) -> None:
        """环形缓冲写入（容量封顶，保留最新）。"""
        self._records.append(rec)
        if len(self._records) > _MAX_RECORDS:
            self._records = self._records[-_MAX_RECORDS:]

    def records(self, limit: int = 50) -> list[dict]:
        """返回最近 limit 条路由记录（时间戳倒序）。"""
        with self._lock:
            rows = self._records[-limit:]
        return [
            {
                "ts": r.ts,
                "request_id": r.request_id,
                "model": r.model,
                "requested_provider": r.requested_provider,
                "selected_provider": r.selected_provider,
                "score": round(r.score, 4),
                "scores": {k: round(v, 4) for k, v in r.scores.items()},
                "latency_ms": r.latency_ms,
                "success": r.success,
                "reason": r.reason,
            }
            for r in rows
        ]

    # ── 统计更新 ──
    def record_result(self, provider_id: str, latency_ms: float, is_success: bool) -> None:
        """记录一次调用结果（时延 + 成败），更新 EWMA 与熔断状态。"""
        with self._lock:
            stats = self.nodes.setdefault(provider_id, ProviderNodeStats(provider_id=provider_id))
            stats.in_flight_requests = max(0, stats.in_flight_requests - 1)
            stats.last_result_ts = time.time()
            if is_success:
                stats.success_count += 1
                stats.consecutive_failures = 0
                stats.ewma_latency_ms = (self.alpha * max(0.0, latency_ms)
                                         + (1 - self.alpha) * stats.ewma_latency_ms)
                if stats.circuit_state == "HALF_OPEN":
                    # HALF_OPEN 时成功一个 → 熔断确认恢复
                    stats.circuit_state = "CLOSED"
            else:
                stats.failure_count += 1
                stats.consecutive_failures += 1
                # 失败惩罚：EWMA 时延放大 1.5x（封顶 5s），快速感知抖动
                stats.ewma_latency_ms = max(_INIT_EWMA, stats.ewma_latency_ms * 1.5)
                # 熔断判定：失败率 > 阈值且样本足够
                total = stats.success_count + stats.failure_count
                if (total >= _OPEN_MIN_SAMPLES
                        and (stats.failure_count / total) > _OPEN_FAIL_RATIO):
                    stats.circuit_state = "OPEN"
                    stats.circuit_open_until = time.time() + _OPEN_COOLDOWN

    def record_inflight(self, provider_id: str, delta: int = 1) -> None:
        """在途请求计数（调用前 +1，结果回来时由 record_result -1）。"""
        with self._lock:
            stats = self.nodes.setdefault(provider_id, ProviderNodeStats(provider_id=provider_id))
            stats.in_flight_requests = max(0, stats.in_flight_requests + delta)

    def record_direct(self, provider_id: str, model_id: str, request_id: str = "") -> None:
        """记录一次「直接路由」决策（selected = requested，不做跨提供商自动降级）。

        供 provider_for 在 healthy/degraded 路径下写入观测记录，前端路由面板据此
        显示该请求真实路由到了请求指定的提供商（reason=direct），而非被自适应偷换。
        """
        with self._lock:
            now = time.time()
            self._record(RoutingRecord(
                ts=now, request_id=request_id, model=model_id,
                selected_provider=provider_id, requested_provider=provider_id,
                score=self._calculate_score(provider_id),
                scores={provider_id: self._calculate_score(provider_id)},
                reason="direct",
            ))

    # ── 核心打分 ──
    def _calculate_score(self, pid: str) -> float:
        st = self.nodes.setdefault(pid, ProviderNodeStats(provider_id=pid))
        total = st.success_count + st.failure_count
        # Laplace 平滑成功率（冷启动不偏 0/1）
        success_rate = (st.success_count + 1.0) / (total + 2.0)
        latency_factor = math.log10(max(_LATENCY_FLOOR, st.ewma_latency_ms))
        load_penalty = 1.0 / (1.0 + 0.1 * st.in_flight_requests)
        return (success_rate / latency_factor) * load_penalty

    def _snapshot_scores(self, candidates: list[str]) -> dict[str, float]:
        return {pid: self._calculate_score(pid) for pid in candidates}

    def _is_available(self, pid: str, now: float) -> tuple[bool, "ProviderNodeStats"]:
        """检查 provider 是否可用（熔断未开/已恢复）。"""
        st = self.nodes.setdefault(pid, ProviderNodeStats(provider_id=pid))
        if st.circuit_state == "OPEN":
            if now >= st.circuit_open_until:
                st.circuit_state = "HALF_OPEN"
                return True, st
            return False, st
        return True, st

    def select_best(self, candidates: list[str], *, request_id: str = "",
                    model: str = "", requested_provider: str = "",
                    explore: bool | None = None) -> str:
        """从候选 provider 中选出路由目标。

        候选应为健康/或已从熔断恢复的 provider。返回选中的 provider_id，
        并写入一条路由记录（request_id/model 便于前端追踪）。
        """
        requested_provider = requested_provider or (candidates[0] if candidates else "")
        if not candidates:
            raise ValueError("select_best 需要至少一个候选")
        now = time.time()

        with self._lock:
            valid = []
            for pid in candidates:
                ok, _ = self._is_available(pid, now)
                if ok:
                    valid.append(pid)
            if not valid:
                # 全部熔断 → 兜底：返回第一个候选（最坏也只是慢，不卡死）
                scores = self._snapshot_scores(candidates)
                picked = candidates[0]
                self._record(RoutingRecord(
                    ts=now, request_id=request_id, model=model,
                    selected_provider=picked, requested_provider=requested_provider,
                    score=scores.get(picked, 0.0), scores=scores,
                    reason="fallback_all_open",
                ))
                self._record_inflight_locked(picked)
                return picked

            # 探索：epsilon 衰减（样本越多探索越少）
            sample_total = sum(
                self.nodes[p].success_count + self.nodes[p].failure_count
                for p in valid if p in self.nodes
            )
            eps = self.base_explore_rate * max(0.05, (1.0 - sample_total / 200.0))
            if explore is not None:
                eps = explore
            # explore=False（测试/确定性路径）时强制不探索；其余默认探索
            do_explore = (eps > 0) and (sample_total < 10 or self._rand() < eps)

            scores = self._snapshot_scores(valid)
            if do_explore:
                # 随机选一个有效候选（探测恢复）
                import random as _random
                picked = valid[int(_random.random() * len(valid))]
                reason = "explore"
            else:
                picked = max(valid, key=lambda pid: scores[pid])
                reason = "best_score"
            self._record(RoutingRecord(
                ts=now, request_id=request_id, model=model,
                selected_provider=picked, requested_provider=requested_provider,
                score=scores.get(picked, 0.0), scores=scores,
                reason=reason,
            ))
            self._record_inflight_locked(picked)
            return picked

    def _record_inflight_locked(self, pid: str) -> None:
        st = self.nodes.setdefault(pid, ProviderNodeStats(provider_id=pid))
        st.in_flight_requests += 1

    @staticmethod
    def _rand() -> float:
        import random as _random
        return _random.random()

    # ── 面板 ──
    def node_snapshot(self) -> dict[str, dict]:
        """所有 provider 的统计快照（前端路由面板展示）。"""
        with self._lock:
            return {
                pid: {
                    "provider_id": pid,
                    "success_count": st.success_count,
                    "failure_count": st.failure_count,
                    "ewma_latency_ms": round(st.ewma_latency_ms, 1),
                    "in_flight_requests": st.in_flight_requests,
                    "circuit_state": st.circuit_state,
                    "circuit_open_until": st.circuit_open_until,
                    "consecutive_failures": st.consecutive_failures,
                    "score": round(self._calculate_score(pid), 4),
                }
                for pid, st in self.nodes.items()
            }

    def reset(self) -> None:
        """清空全部统计（测试 / 运维用）。"""
        with self._lock:
            self.nodes = {}
            self._records = []


# 模块级单例（registry 启动时挂载）
adaptive_router = AdaptiveRouter()