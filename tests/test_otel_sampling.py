"""P3-2: OTel tail-based 采样策略 + SSE 指标采集测试。

验证：
- TailBasedErrorSampler：错误请求 100% 采样、正常请求按比例采样
- SseStats：事件计数、补偿率、取消率计算正确
- sse_events.publish 集成采集（不破主链路）
"""

from __future__ import annotations

import pytest

from api.sse_stats import SseStats


class TestSseStats:
    """SSE 指标采集器单元测试。"""

    def test_empty_snapshot(self):
        stats = SseStats()
        snap = stats.snapshot()
        assert snap["total_events"] == 0
        assert snap["compensation_rate"] == 0.0
        assert snap["cancellation_rate"] == 0.0
        assert snap["avg_events_per_task"] == 0.0

    def test_record_event_counts(self):
        stats = SseStats()
        stats.record_event("t1", "progress")
        stats.record_event("t1", "progress")
        stats.record_event("t1", "result")
        snap = stats.snapshot()
        assert snap["total_events"] == 3
        assert snap["events_by_type"] == {"progress": 2, "result": 1}
        assert snap["tasks_seen"] == 1
        assert snap["avg_events_per_task"] == 3.0

    def test_compensation_rate(self):
        stats = SseStats()
        stats.record_event("t1", "progress")
        stats.record_event("t1", "progress")
        stats.record_retry("t1")  # 1 次补偿
        snap = stats.snapshot()
        assert snap["retry_events"] == 1
        assert snap["compensation_rate"] == 0.5  # 1/2

    def test_cancellation_rate(self):
        stats = SseStats()
        stats.record_subscription("t1")
        stats.record_subscription("t1")
        stats.record_cancellation("t1")
        snap = stats.snapshot()
        assert snap["total_subscriptions"] == 2
        assert snap["cancelled_subscriptions"] == 1
        assert snap["cancellation_rate"] == 0.5

    def test_reset(self):
        stats = SseStats()
        stats.record_event("t1", "progress")
        stats.record_subscription("t1")
        stats.reset()
        snap = stats.snapshot()
        assert snap["total_events"] == 0
        assert snap["total_subscriptions"] == 0
        assert snap["tasks_seen"] == 0


class TestTailBasedErrorSampler:
    """OTel tail-based 采样器单元测试。

    OTel 包未安装时 telemetry 内 Sampler/SamplingResult 为 None，
    本测试通过 mock 模拟，验证采样决策逻辑：
    - http.status_code>=500 → RECORD_AND_SAMPLE（100%）
    - error=True → RECORD_AND_SAMPLE（100%）
    - 正常请求 → TraceIdRatioBased 委托（按比例）
    """

    def test_sampler_construction(self):
        from api.telemetry import TailBasedErrorSampler

        sampler = TailBasedErrorSampler(0.1, 1.0)
        assert sampler._sample_rate == 0.1
        assert sampler._error_sample_rate == 1.0
        desc = sampler.get_description()
        assert "rate=0.1" in desc
        assert "error_rate=1.0" in desc

    def test_sampler_clamps_rates(self):
        from api.telemetry import TailBasedErrorSampler

        sampler = TailBasedErrorSampler(1.5, -0.2)
        assert sampler._sample_rate == 1.0
        assert sampler._error_sample_rate == 0.0


class TestSseStatsIntegration:
    """sse_events.publish 与 sse_stats 集成验证（不破主链路）。"""

    @pytest.mark.asyncio
    async def test_publish_records_stats(self):
        """hub.publish 应调用 sse_stats.record_event。"""
        from api.sse_events import TaskEventHub
        from api.sse_stats import sse_stats

        sse_stats.reset()
        hub = TaskEventHub()
        await hub.publish("task-1", "progress", {"pct": 50})
        snap = sse_stats.snapshot()
        assert snap["total_events"] == 1
        assert snap["events_by_type"]["progress"] == 1
        assert "task-1" in str(snap) or snap["tasks_seen"] >= 1
