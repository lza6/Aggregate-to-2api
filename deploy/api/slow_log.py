"""慢日志画像引擎（v3.1.0 S-3 / P-C2）：分阶段耗时的环形缓冲采样。

定位「出图慢在哪」：排队久（queue）/ 等 token 久（wait_token）/ Turnstile 求解久
（solve）/ 上游调用久（upstream）/ 重试累计（retry）。内存环形缓冲，不落盘——
配合 /v1/slow 端点与看板实时查看；进程重启即清零，符合诊断数据语义。

线程安全：asyncio 场景下 record 均为同步短临界区，用 threading.Lock 保护
（worker 池虽在同一事件循环，但 snapshot 可能被任意线程的端点调用）。
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

# 阶段名 → SlowSample 字段名（stats 阶段分布用）
_STAGES: tuple[tuple[str, str], ...] = (
    ("queue", "queue_ms"),
    ("wait_token", "wait_token_ms"),
    ("solve", "solve_ms"),
    ("upstream", "upstream_ms"),
    ("retry", "retry_ms"),
)


@dataclass(slots=True)
class SlowSample:
    """单条慢请求画像样本（各阶段耗时毫秒）。

    trace_id：全链路统一追踪 id（B2），入口请求的 request_id/trace_id 透传而来，
    可 grep 串联该任务的日志/审计/慢日志。缺省空串（向后兼容旧调用方）。

    B3: submit_ms（上游提交首字节）、poll_ms（轮询到完成）为慢请求完整链路采样的
    分段细化，供 /v1/slow/view 分位段树展示。
    """

    task_id: str
    model: str
    provider: str
    queue_ms: float = 0.0          # 入队 → worker 取走
    wait_token_ms: float = 0.0     # 取 token 等待
    solve_ms: float = 0.0          # Turnstile 求解耗时
    upstream_ms: float = 0.0       # 上游提交+轮询
    retry_ms: float = 0.0          # 重试退避累计
    total_ms: float = 0.0          # 全程
    status: str = "completed"      # completed / error
    trace_id: str = ""             # B2: 全链路 traceId（日志/审计/慢日志 grep 串联）
    submit_ms: float = 0.0         # B3: 上游提交首字节耗时
    poll_ms: float = 0.0           # B3: 上游轮询到完成耗时
    created_at: float = field(default_factory=time.time)

    def slowest_stage(self) -> str:
        """耗时最大的阶段名（全零时返回 "total"）。"""
        best, best_v = "total", -1.0
        for name, attr in _STAGES:
            v = getattr(self, attr)
            if v > best_v:
                best, best_v = name, v
        return best if best_v > 0 else "total"


class SlowLog:
    """阈值过滤 + 有界环形缓冲的慢请求记录器。

    enabled=False 时 record 直接丢弃（生产可一键关闭）；
    超容量淘汰最旧；所有方法 O(1)（stats 为 O(n)，n≤maxsize）。
    """

    def __init__(self, enabled: bool = True, threshold_ms: float = 5000.0,
                 maxsize: int = 500):
        self._enabled = enabled
        self._threshold_ms = threshold_ms
        self._buf: deque[SlowSample] = deque(maxlen=max(1, maxsize))
        self._lock = threading.Lock()

    def record(self, sample: SlowSample) -> None:
        """记录一条样本：低于阈值或未启用时静默丢弃（幂等无副作用）。"""
        if not self._enabled or sample.total_ms < self._threshold_ms:
            return
        with self._lock:
            self._buf.append(sample)

    def snapshot(self) -> list[SlowSample]:
        """按写入序返回全部慢样本副本（最旧在前）。"""
        with self._lock:
            return list(self._buf)

    def stats(self) -> dict:
        """聚合统计：条数/均值/最大值/最慢阶段（diagnostics 与看板用）。"""
        with self._lock:
            items = list(self._buf)
        if not items:
            return {"count": 0, "avg_total_ms": 0.0, "max_total_ms": 0.0,
                    "slowest_stage": None}
        totals = [s.total_ms for s in items]
        slowest = max(items, key=lambda s: s.total_ms)
        return {
            "count": len(items),
            "avg_total_ms": round(sum(totals) / len(totals), 1),
            "max_total_ms": round(max(totals), 1),
            "slowest_stage": slowest.slowest_stage(),
        }


# ── 模块级单例（main/worker 打点共享；配置由 config.IF_SLOW_* 注入）───────
slow_log = SlowLog()
