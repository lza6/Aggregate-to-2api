"""集成测试：异步提交 + 轮询结果。"""
import asyncio
import pytest


@pytest.mark.integration
class TestAsyncFlow:
    """异步任务提交、轮询、列表查询、404 场景。"""

    async def test_async_submit_and_poll(self, app_with_mocks):
        """异步提交后轮询直到终态。"""
        client = app_with_mocks
        r = await client.post("/v1/generate/async", json={
            "prompt": "a dog", "aspect_ratio": "1:1", "model": "imagefree/default",
        })
        assert r.status_code == 200
        body = r.json()
        assert "id" in body
        task_id = body["id"]
        assert body.get("status") in ("pending", "processing")
        for _ in range(30):
            r = await client.get(f"/v1/tasks/{task_id}")
            assert r.status_code == 200
            t = r.json()
            if t.get("status") == "completed":
                return
            if t.get("status") == "error":
                pytest.fail(f"任务失败: {t.get('error')}")
            await asyncio.sleep(0.3)
        pytest.fail("异步任务超时未完成")

    async def test_task_list_endpoint(self, app_with_mocks):
        """任务列表端点返回提交的任务。"""
        r = await app_with_mocks.post("/v1/generate/async", json={
            "prompt": "test list", "aspect_ratio": "1:1",
        })
        assert r.status_code == 200
        r = await app_with_mocks.get("/v1/tasks")
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert len(body["items"]) >= 1

    async def test_task_not_found(self, app_with_mocks):
        """不存在的任务 ID 返回 404。"""
        r = await app_with_mocks.get("/v1/tasks/nonexistent-id")
        assert r.status_code == 404