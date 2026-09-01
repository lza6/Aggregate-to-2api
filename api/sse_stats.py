"""P3-2: SSE 事件流指标采集 + /v1/sse/stats 只读端点。

采集维度：
- 每任务事件推送总量（按 event 类型分桶）
- 补偿率 = retry 事件数 / 总事件数（客户端 Last-Event-ID 重连触发的 replay）
- 流式取消率 = 客户端断开数 / 总订阅数

设计：
- 模块级单例 SseStats，纯内存原子计数（threading.Lock 保护，调用方同步）
- 向后兼容：默认采集但不影响 SSE 主链路（计数失败静默）
- 端点 /v1/sse/stats 只读，需 admin key（routes/admin.py 挂载）
"""

from __future__ import annotations

import threading
import time

# 同 sse_events 的 MAX_EVENTS_PER_TASK 对齐，此处仅用于快照任务数估算
_MAX_EVENTS_PER_TASK_SNAPSHOT = 50


class SseStats:
    """SSE 事件流指标采集器（模块级单例）。

    线程安全：所有计数器操作在 self._lock 临界区内完成。
    调用方：sse_events.publish / task_events_generator 在主链路同步调用，
    计数失败静默吞掉（绝不影响 SSE 推送）。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total_events = 0
        self._events_by_type: dict[str, int] = {}
        self._retry_events = 0  # 客户端 Last-Event-ID 补偿回放计数
        self._total_subscriptions = 0
        self._cancelled_subscriptions = 0
        self._tasks_seen: set[str] = set()
        self._started_at = time.time()

    def record_event(self, task_id: str, event: str) -> None:
        """记录一次事件推送（publish 调用点）。"""
        try:
            with self._lock:
                self._total_events += 1
                self._events_by_type[event] = self._events_by_type.get(event, 0) + 1
                self._tasks_seen.add(task_id)
        except Exception:
            pass

    def record_retry(self, task_id: str) -> None:
        """记录一次 Last-Event-ID 补偿回放（断线重连 replay）。"""
        try:
            with self._lock:
                self._retry_events += 1
        except Exception:
            pass

    def record_subscription(self, task_id: str) -> None:
        """记录一次订阅开始。"""
        try:
            with self._lock:
                self._total_subscriptions += 1
                self._tasks_seen.add(task_id)
        except Exception:
            pass

    def record_cancellation(self, task_id: str) -> None:
        """记录一次客户端主动断开/取消。"""
        try:
            with self._lock:
                self._cancelled_subscriptions += 1
        except Exception:
            pass

    def snapshot(self) -> dict:
        """返回只读快照（供 /v1/sse/stats 端点）。"""
        with self._lock:
            total = self._total_events
            retry = self._retry_events
            subs = self._total_subscriptions
            cancelled = self._cancelled_subscriptions
            tasks = len(self._tasks_seen)
            events_by_type = dict(self._events_by_type)
        return {
            "total_events": total,
            "events_by_type": events_by_type,
            "retry_events": retry,
            "compensation_rate": round(retry / total, 4) if total > 0 else 0.0,
            "total_subscriptions": subs,
            "cancelled_subscriptions": cancelled,
            "cancellation_rate": round(cancelled / subs, 4) if subs > 0 else 0.0,
            "tasks_seen": tasks,
            "avg_events_per_task": round(total / tasks, 2) if tasks > 0 else 0.0,
            "uptime_seconds": round(time.time() - self._started_at, 1),
        }

    def reset(self) -> None:
        """测试钩子：重置所有计数器。"""
        with self._lock:
            self._total_events = 0
            self._events_by_type.clear()
            self._retry_events = 0
            self._total_subscriptions = 0
            self._cancelled_subscriptions = 0
            self._tasks_seen.clear()
            self._started_at = time.time()


# 模块级单例
sse_stats = SseStats()
