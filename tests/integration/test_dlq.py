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