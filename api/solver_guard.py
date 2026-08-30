"""Turnstile 求解质量观测 + 集群节点故障熔断调度 (Solver Node Federation)。

所有求解路径（token 池预取、文生图直连、图生图代理）在 turnstile_client.solve_turnstile
内部统一调度并上报到这里：

- 集群级与单节点观测：追踪每个 solver 节点的健康状态、连续失败数、429 状态、在途请求量 (inflight)、平均耗时。
- 调度策略：加权与最少在途轮询 (Weighted Least-Inflight Selection / Failover)。
- 熔断机制：
  - 当某个节点返回 429 时，自动将该节点熔断 rate_limit_cooldown（默认 60s）；
  - 当某个节点连续失败达到 threshold 时，熔断 probe_interval 秒；
  - 恢复后通过 half-open 探测放行一个请求，探测成功即恢复 CLOSED；
  - 若所有节点均不可用，集群整体进入 OPEN 状态并按周期放行探测。
- 暴露：snapshot() 供 /healthz, /v1/stats 与 /metrics 消费，包含 nodes 明细。
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any, Sequence

from . import config

log = logging.getLogger("solver_guard")

# 失败原因分类（与 turnstile_client 上报对齐）
REASON_CATEGORIES = ("timeout", "transport", "http_error", "rate_limit", "solver_rejected", "other")


class SolverNodeState:
    """单个 Solver 节点的状态机与指标追踪。"""

    def __init__(
        self,
        url: str,
        weight: int = 1,
        circuit_threshold: int = 5,
        probe_interval: float = 30.0,
        rate_limit_cooldown: float = 60.0,
        window_seconds: float = 300.0,
        window_maxlen: int = 5000,
    ) -> None:
        self.url = url.rstrip("/")
        self.weight = max(1, weight)
        self.circuit_threshold = circuit_threshold
        self.probe_interval = probe_interval
        self.rate_limit_cooldown = rate_limit_cooldown
        self.window_seconds = window_seconds
        self.window_maxlen = window_maxlen
        self._reset()

    def _reset(self) -> None:
        self._success = 0
        self._failure = 0
        self._total_duration = 0.0
        self._reasons: dict[str, int] = {}
        self._window: deque = deque(maxlen=self.window_maxlen)
        self._consecutive_failures = 0
        self._last_failure_at: float | None = None
        self._circuit_open = False
        self._circuit_opened_at: float | None = None
        self._last_probe_at = 0.0
        self._inflight = 0
        self._rate_limited_until = 0.0
        self._rate_limit_count = 0

    @property
    def inflight(self) -> int:
        return self._inflight

    @property
    def circuit_open(self) -> bool:
        # 如果是因为连续失败熔断或者 429 限流
        now = time.time()
        if self._rate_limited_until > now:
            return True
        return self._circuit_open

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def acquire_inflight(self) -> None:
        self._inflight += 1

    def release_inflight(self) -> None:
        self._inflight = max(0, self._inflight - 1)

    def is_rate_limited(self) -> bool:
        return time.time() < self._rate_limited_until

    def allow_solve(self) -> bool:
        """检查节点是否允许发起请求。支持 429 冷却与 half-open 探测。"""
        now = time.time()
        if self._rate_limited_until > now:
            return False
        if not self._circuit_open:
            return True
        if now - self._last_probe_at >= self.probe_interval:
            self._last_probe_at = now
            log.info("solver node [%s] half-open: 放行一个探测求解", self.url)
            return True
        return False

    def record_success(self, duration_sec: float) -> None:
        self._success += 1
        self._total_duration += duration_sec
        self._consecutive_failures = 0
        self._window.append((time.time(), True, duration_sec))
        if self._circuit_open:
            self._circuit_open = False
            self._circuit_opened_at = None
            log.info("solver node [%s] 熔断恢复: 探测求解成功, 回到 CLOSED", self.url)
        self._rate_limited_until = 0.0
        self._trim_window()

    def record_failure(self, reason: str, duration_sec: float | None = None) -> None:
        cat = reason if reason in REASON_CATEGORIES else "other"
        self._failure += 1
        self._reasons[cat] = self._reasons.get(cat, 0) + 1
        self._consecutive_failures += 1
        now = time.time()
        self._last_failure_at = now
        if duration_sec is not None:
            self._window.append((now, False, duration_sec))
        self._trim_window()

        if reason == "rate_limit":
            self._rate_limit_count += 1
            self._rate_limited_until = now + self.rate_limit_cooldown
            log.warning("solver node [%s] 命中 429 限流, 熔断冷却 %.0fs", self.url, self.rate_limit_cooldown)
        elif not self._circuit_open and self._consecutive_failures >= self.circuit_threshold:
            self._circuit_open = True
            self._circuit_opened_at = now
            log.warning(
                "solver node [%s] 熔断 OPEN（连续 %d 次失败）, 暂停新求解, %.0fs 后放行探测",
                self.url,
                self._consecutive_failures,
                self.probe_interval,
            )

    def _trim_window(self) -> None:
        cutoff = time.time() - self.window_seconds
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        success_total = self._success
        failure_total = self._failure
        solve_total = success_total + failure_total
        win = [x for x in self._window if now - x[0] <= self.window_seconds]
        win_ok = sum(1 for _, ok, _ in win if ok)
        win_dur = sum(d for _, _, d in win)
        is_rl = self._rate_limited_until > now
        status = (
            "circuit_open"
            if (self._circuit_open or is_rl)
            else ("degraded" if self._consecutive_failures > 0 else "ok")
        )

        return {
            "url": self.url,
            "weight": self.weight,
            "inflight": self._inflight,
            "status": status,
            "circuit_open": self.circuit_open,
            "circuit_opened_at": self._circuit_opened_at,
            "rate_limited": is_rl,
            "rate_limited_remaining_sec": max(0.0, round(self._rate_limited_until - now, 1)) if is_rl else 0.0,
            "solve_total": solve_total,
            "solve_success_total": success_total,
            "solve_failure_total": failure_total,
            "solve_avg_seconds": round(self._total_duration / success_total, 2) if success_total else None,
            "failure_reasons": dict(self._reasons),
            "window_success_rate": round(win_ok / len(win), 4) if win else None,
            "window_solve_count": len(win),
            "window_avg_seconds": round(win_dur / len(win), 2) if win else None,
            "consecutive_failures": self._consecutive_failures,
            "last_failure_at": self._last_failure_at,
        }


class SolverGuard:
    """集群级 SolverGuard，全面管理多节点调度、负载均衡、熔断与统计。"""

    def __init__(
        self,
        circuit_threshold: int = 5,
        probe_interval: float = 30.0,
        window_seconds: float = 300.0,
        window_maxlen: int = 10000,
        urls: Sequence[str] | None = None,
        weights: dict[str, int] | None = None,
        rate_limit_cooldown: float = 60.0,
    ) -> None:
        self.circuit_threshold = circuit_threshold
        self.probe_interval = probe_interval
        self.window_seconds = window_seconds
        self.window_maxlen = window_maxlen
        self.rate_limit_cooldown = rate_limit_cooldown

        self._nodes: dict[str, SolverNodeState] = {}
        self._global_rejected_total = 0
        self._rr_index = 0

        # 初始化节点
        init_urls = list(urls) if urls else [config.CF_SOLVER_URL]
        init_weights = weights or {}
        self.configure_nodes(init_urls, init_weights)
        self._reset_global_stats()

    def _reset_global_stats(self) -> None:
        """重置全局聚合指标。"""
        self._global_success = 0
        self._global_failure = 0
        self._global_total_duration = 0.0
        self._global_reasons: dict[str, int] = {}
        self._global_window: deque = deque(maxlen=self.window_maxlen)
        self._global_rejected_total = 0

    def _reset(self) -> None:
        """清空全部状态（兼容原单机测试与重置）。"""
        self._reset_global_stats()
        for node in self._nodes.values():
            node._reset()

    def configure_nodes(self, urls: Sequence[str], weights: dict[str, int] | None = None) -> None:
        """动态配置或更新节点池列表。"""
        weights = weights or {}
        cleaned_urls = [u.rstrip("/") for u in urls if u and u.strip()]
        if not cleaned_urls:
            cleaned_urls = [config.CF_SOLVER_URL.rstrip("/")]

        new_nodes: dict[str, SolverNodeState] = {}
        for u in cleaned_urls:
            w = weights.get(u, 1)
            if u in self._nodes:
                existing = self._nodes[u]
                existing.weight = max(1, w)
                new_nodes[u] = existing
            else:
                new_nodes[u] = SolverNodeState(
                    url=u,
                    weight=w,
                    circuit_threshold=self.circuit_threshold,
                    probe_interval=self.probe_interval,
                    rate_limit_cooldown=self.rate_limit_cooldown,
                    window_seconds=self.window_seconds,
                    window_maxlen=self.window_maxlen,
                )
        self._nodes = new_nodes

    def get_nodes(self) -> list[SolverNodeState]:
        return list(self._nodes.values())

    def acquire_inflight_for(self, url: str) -> SolverNodeState | None:
        """通过 URL 获取节点状态并标记在途请求（公共方法，避免外部访问私有 _nodes）。"""
        cleaned = url.rstrip("/")
        node = self._nodes.get(cleaned)
        if node:
            node.acquire_inflight()
        return node

    def release_inflight_for(self, url: str) -> None:
        """通过 URL 释放节点在途请求计数。"""
        cleaned = url.rstrip("/")
        node = self._nodes.get(cleaned)
        if node:
            node.release_inflight()

    def select_node(self) -> SolverNodeState | None:
        """选择最优健康节点：加权与最少在途 (Weighted Least-Inflight Selection)。

        若所有节点均 OPEN/熔断，则尝试放行处于 half-open 探测周期的节点。
        若均不可用返回 None。
        """
        available = [n for n in self._nodes.values() if n.allow_solve()]
        if not available:
            return None

        # 评分计算：inflight / weight 越小越好；同分下 round-robin
        # 增加轻微的 round-robin 扰动打破并列
        def _score(n: SolverNodeState) -> float:
            return n.inflight / float(n.weight)

        available.sort(key=_score)
        min_score = _score(available[0])
        # 找出所有与最小分数相近的候选集
        candidates = [n for n in available if _score(n) == min_score]

        self._rr_index = (self._rr_index + 1) % len(candidates)
        return candidates[self._rr_index]

    def select_candidates(self, exclude_urls: set[str] | None = None) -> list[SolverNodeState]:
        """获取按健康度和负载排序的备选节点列表，用于快速故障转移 (failover)。"""
        exclude = exclude_urls or set()
        available = [n for n in self._nodes.values() if n.url not in exclude and n.allow_solve()]
        if not available:
            # 如果没有正常节点，尝试包含处于熔断但可探测的节点
            available = [n for n in self._nodes.values() if n.url not in exclude and not n.is_rate_limited()]

        def _score(n: SolverNodeState) -> tuple[int, float]:
            # (是否熔断, inflight/weight)
            return (1 if n.circuit_open else 0, n.inflight / float(n.weight))

        available.sort(key=_score)
        return available

    # ── 上报（支持单机上报与指定 node_url 上报）──────────
    def record_success(self, duration_sec: float, node_url: str | None = None) -> None:
        """记录求解成功。"""
        self._global_success += 1
        self._global_total_duration += duration_sec
        self._global_window.append((time.time(), True, duration_sec))
        self._trim_global_window()

        if node_url:
            cleaned = node_url.rstrip("/")
            if cleaned in self._nodes:
                self._nodes[cleaned].record_success(duration_sec)
        else:
            # 未指定节点（如单机旧测试），若只有 1 个节点则同步更新
            if len(self._nodes) == 1:
                list(self._nodes.values())[0].record_success(duration_sec)

    def record_failure(self, reason: str, duration_sec: float | None = None, node_url: str | None = None) -> None:
        """记录求解失败。"""
        cat = reason if reason in REASON_CATEGORIES else "other"
        self._global_failure += 1
        self._global_reasons[cat] = self._global_reasons.get(cat, 0) + 1
        now = time.time()
        if duration_sec is not None:
            self._global_window.append((now, False, duration_sec))
        self._trim_global_window()

        if node_url:
            cleaned = node_url.rstrip("/")
            if cleaned in self._nodes:
                self._nodes[cleaned].record_failure(reason, duration_sec)
        else:
            if len(self._nodes) == 1:
                list(self._nodes.values())[0].record_failure(reason, duration_sec)

    def record_rejected(self) -> None:
        """token 解出但被上游 imagefree 拒绝。"""
        self._global_rejected_total += 1

    # ── 兼容原单机属性与方法 ───────────────────────────
    def allow_solve(self) -> bool:
        """是否存在至少一个可求解节点。"""
        return any(node.allow_solve() for node in self._nodes.values())

    @property
    def circuit_open(self) -> bool:
        """集群是否全部熔断。"""
        if not self._nodes:
            return False
        return all(node.circuit_open for node in self._nodes.values())

    @property
    def consecutive_failures(self) -> int:
        """返回所有节点中最大连续失败数。"""
        if not self._nodes:
            return 0
        return max(node.consecutive_failures for node in self._nodes.values())

    # ── 统计快照（healthz/metrics 消费）────────────────
    def snapshot(self) -> dict[str, Any]:
        success_total = self._global_success
        failure_total = self._global_failure
        solve_total = success_total + failure_total
        now = time.time()
        win = [x for x in self._global_window if now - x[0] <= self.window_seconds]
        win_ok = sum(1 for _, ok, _ in win if ok)
        win_dur = sum(d for _, _, d in win)

        node_snaps = [n.snapshot() for n in self._nodes.values()]
        any_open = any(n["circuit_open"] for n in node_snaps)
        all_open = bool(node_snaps and all(n["circuit_open"] for n in node_snaps))
        max_consecutive = max((n["consecutive_failures"] for n in node_snaps), default=0)
        last_failure = max((n["last_failure_at"] for n in node_snaps if n["last_failure_at"] is not None), default=None)
        opened_at = min(
            (n["circuit_opened_at"] for n in node_snaps if n["circuit_opened_at"] is not None), default=None
        )

        cluster_status = "circuit_open" if all_open else ("degraded" if (any_open or max_consecutive > 0) else "ok")

        return {
            "solve_total": solve_total,
            "solve_success_total": success_total,
            "solve_failure_total": failure_total,
            "solve_avg_seconds": round(self._global_total_duration / success_total, 2) if success_total else None,
            "solve_total_duration": round(self._global_total_duration, 3),
            "failure_reasons": dict(self._global_reasons),
            "window_success_rate": round(win_ok / len(win), 4) if win else None,
            "window_solve_count": len(win),
            "window_avg_seconds": round(win_dur / len(win), 2) if win else None,
            "consecutive_failures": max_consecutive,
            "last_failure_at": last_failure,
            "circuit_open": all_open,
            "circuit_opened_at": opened_at,
            "rejected_total": self._global_rejected_total,
            "solver_status": cluster_status,
            "nodes": node_snaps,
            "node_count": len(self._nodes),
            "healthy_node_count": sum(1 for n in node_snaps if not n["circuit_open"]),
        }

    def _trim_global_window(self) -> None:
        cutoff = time.time() - self.window_seconds
        while self._global_window and self._global_window[0][0] < cutoff:
            self._global_window.popleft()


# 模块级单例（全服务共享；阈值从配置读取；测试可用 _reset() 重置或用独立实例）
solver_guard = SolverGuard(
    circuit_threshold=config.SOLVE_CIRCUIT_THRESHOLD,
    probe_interval=config.SOLVE_CIRCUIT_PROBE_SECONDS,
    window_seconds=config.SOLVE_STATS_WINDOW_SECONDS,
    urls=getattr(config, "CF_SOLVER_URLS", [config.CF_SOLVER_URL]),
    weights=getattr(config, "SOLVER_NODE_WEIGHTS", {}),
    rate_limit_cooldown=getattr(config, "SOLVER_RATE_LIMIT_COOLDOWN_SECONDS", 60.0),
)
