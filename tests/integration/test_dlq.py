"""集成测试：死信队列行为验证。"""

import pytest


@pytest.mark.integration
class TestDLQ:
    """死信队列端点基本功能。"""

    async def test_dlq_endpoints(self, app_with_mocks):
        """死信队列查询返回 items 和 count。"""
        client = app_with_mocks
        r = await client.get("/v1/dead-letter-queue")
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "count" in body


@pytest.mark.integration
class TestDLQRetryFlow:
    """P-TEST-A8: DLQ retry 端点行为（记录移除语义）。"""

    async def test_retry_nonexistent_task_ok(self, app_with_mocks):
        """重试不存在的任务：幂等返回 ok（retry_dlq 只删，删 0 行也是 ok）。"""
        r = await app_with_mocks.post("/v1/dead-letter-queue/nonexistent-task-id/retry")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    async def test_clear_then_list_empty(self, app_with_mocks):
        """清空后列表 count=0。"""
        r = await app_with_mocks.delete("/v1/dead-letter-queue")
        assert r.status_code == 200
        r2 = await app_with_mocks.get("/v1/dead-letter-queue")
        assert r2.status_code == 200
        assert r2.json().get("count") == 0


@pytest.mark.integration
class TestDLQRequeue:
    """S-9: DLQ 真重入队（IF_DLQ_REQUEUE 开关两态）。

    集成环境默认 IF_DLQ_REQUEUE=0 → 走旧行为（只删记录）；
    requeue 引擎方法单测在 tests/test_dead_letter_queue.py 覆盖。
    """

    async def test_requeue_disabled_removes_record(self, app_with_mocks):
        """默认关闭：retry 只删记录，不入队。"""
        from api import config as cfg

        assert cfg.IF_DLQ_REQUEUE is False
        r = await app_with_mocks.post("/v1/dead-letter-queue/some-task/retry")
        assert r.status_code == 200
        assert "移除" in r.json()["detail"]
