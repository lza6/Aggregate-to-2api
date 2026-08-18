"""Turnstile 求解质量观测 + 熔断器。

所有求解路径（token 池预取、文生图直连、图生图代理）在 turnstile_client.solve_turnstile
内部统一上报到这里，聚合统计并驱动熔断：

- 统计：成功/失败总数、分原因失败、平均耗时、最近窗口（默认 5 分钟）成功率/吞吐 → 健康趋势。
- 熔断：连续失败达到阈值 → OPEN，暂停所有新求解请求（保护 cf_solver + 避免 worker 空转干等）；
  周期性放行一个探测请求（half-open），探测成功即恢复 CLOSED。
- 暴露：snapshot() 供 /healthz 与 /metrics 消费。

线程安全说明：全部调用发生在同一个 asyncio 事件循环线程内（httpx 异步回调不换线程），
故无需加锁。测试通过 _reset() 重置状态。
"""
import logging
import time
from collections import deque

from . import config

log = logging.getLogger("solver_guard")

# 失败原因分类（与 turnstile_client 上报对齐）
REASON_CATEGORIES = ("timeout", "transport", "http_error", "solver_rejected", "other")


class SolverGuard:
    def __init__(self, circuit_threshold: int = 5, probe_interval: float = 30.0,
                 window_seconds: float = 300.0, window_maxlen: int = 10000) -> None:
        self.circuit_threshold = circuit_threshold
        self.probe_interval = probe_interval
        self.window_seconds = window_seconds
        self.window_maxlen = window_maxlen
        self._reset()

    def _reset(self) -> None:
        """清空全部状态（测试用；也用于首次初始化）。"""
        self._success = 0
        self._failure = 0
        self._total_duration = 0.0
        self._reasons: dict[str, int] = {}
        self._window: deque = deque(maxlen=self.window_maxlen)
        self._consecutive_failures = 0
        self._last_failure_at: float | None = None
        self._rejected_total = 0
        self._circuit_open = False
        self._circuit_opened_at: float | None = None
        self._last_probe_at = 0.0

    # ── 上报（turnstile_client 调用）──────────────────
    def record_success(self, duration_sec: float) -> None:
        self._success += 1
        self._total_duration += duration_sec
        self._consecutive_failures = 0
        self._window.append((time.time(), True, duration_sec))
        if self._circuit_open:  # half-open 探测成功 → 恢复
            self._circuit_open = False
            self._circuit_opened_at = None
            log.info("solver 熔断恢复：探测求解成功，回到 CLOSED")
        self._trim_window()

    def record_failure(self, reason: str, duration_sec: float | None = None) -> None:
        cat = reason if reason in REASON_CATEGORIES else "other"
        self._failure += 1
        self._reasons[cat] = self._reasons.get(cat, 0) + 1
        self._consecutive_failures += 1
        self._last_failure_at = time.time()
        if duration_sec is not None:
            self._window.append((time.time(), False, duration_sec))
        self._trim_window()
        if not self._circuit_open and self._consecutive_failures >= self.circuit_threshold:
            self._circuit_open = True
            self._circuit_opened_at = time.time()
            log.warning("solver 熔断 OPEN（连续 %d 次失败），暂停新求解，%.0fs 后放行探测",
                        self._consecutive_failures, self.probe_interval)

    def record_rejected(self) -> None:
        """token 解出但被上游 imagefree 拒绝（换 token 重试信号），单独计数。"""
        self._rejected_total += 1

    # ── 熔断门控（worker/池 调用）─────────────────────
    def allow_solve(self) -> bool:
        """是否允许发起新求解。OPEN 时每 probe_interval 放行一个探测请求（half-open）。"""
        if not self._circuit_open:
            return True
        now = time.time()
        if now - self._last_probe_at >= self.probe_interval:
            self._last_probe_at = now
            log.info("solver half-open：放行一个探测求解")
            return True
        return False

    @property
    def circuit_open(self) -> bool:
        return self._circuit_open

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    # ── 统计快照（healthz/metrics 消费）────────────────
    def snapshot(self) -> dict:
        success_total = self._success
        failure_total = self._failure
        solve_total = success_total + failure_total
        win = [x for x in self._window if time.time() - x[0] <= self.window_seconds]
        win_ok = sum(1 for _, ok, _ in win if ok)
        win_dur = sum(d for _, _, d in win)
        return {
            "solve_total": solve_total,
            "solve_success_total": success_total,
            "solve_failure_total": failure_total,
            "solve_avg_seconds": round(self._total_duration / success_total, 2) if success_total else None,
            # 原始总耗时（未取整），/metrics 的 _sum 用它，避免「round(avg)×count」累计误差
            "solve_total_duration": round(self._total_duration, 3),
            "failure_reasons": dict(self._reasons),
            "window_success_rate": round(win_ok / len(win), 4) if win else None,
            "window_solve_count": len(win),
            "window_avg_seconds": round(win_dur / len(win), 2) if win else None,
            "consecutive_failures": self._consecutive_failures,
            "last_failure_at": self._last_failure_at,
            "circuit_open": self._circuit_open,
            "circuit_opened_at": self._circuit_opened_at,
            "rejected_total": self._rejected_total,
            "solver_status": ("circuit_open" if self._circuit_open
                              else "degraded" if self._consecutive_failures > 0 else "ok"),
        }

    def _trim_window(self) -> None:
        cutoff = time.time() - self.window_seconds
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()


# 模块级单例（全服务共享；阈值从配置读取；测试可用 _reset() 重置或用独立实例）
solver_guard = SolverGuard(
    circuit_threshold=config.SOLVE_CIRCUIT_THRESHOLD,
    probe_interval=config.SOLVE_CIRCUIT_PROBE_SECONDS,
    window_seconds=config.SOLVE_STATS_WINDOW_SECONDS,
)
