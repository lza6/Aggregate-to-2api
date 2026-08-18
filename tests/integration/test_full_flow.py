"""集成测试：完整文生图流程（全 mock 模式）。"""
import asyncio
import pytest


@pytest.mark.integration
class TestFullFlow:
    """端到端文生图 + 健康检查 + 模型列表 + 统计 + 画廊。"""

    async def test_txt2img_complete_flow(self, app_with_mocks):
        """同步提交文生图，轮询直到终态。"""
        client = app_with_mocks
        r = await client.post("/v1/generate", json={
            "prompt": "a cat", "aspect_ratio": "1:1", "model": "imagefree/default",
        })
        assert r.status_code in (200, 202)
        body = r.json()
        assert "id" in body
        assert body.get("status") in ("completed", "processing", "queued")
        if body.get("status") == "completed":
            assert body.get("image_url") or body.get("image_base64")
            return
        task_id = body["id"]
        for _ in range(30):
            r = await client.get(f"/v1/tasks/{task_id}")
            assert r.status_code == 200
            t = r.json()
            if t.get("status") == "completed":
                assert t.get("image_url") or t.get("image_base64")
                return
            if t.get("status") == "error":
                pytest.fail(f"任务失败: {t.get('error')}")
            await asyncio.sleep(0.3)
        pytest.fail("任务超时未完成")

    async def test_healthz_returns_ok(self, app_with_mocks):
        """健康检查端点返回 ok/degraded。"""
        r = await app_with_mocks.get("/v1/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") in ("ok", "degraded")
        assert "cf_solver" in body
        assert "processing" in body
        assert "queued" in body
        assert "workers" in body
        assert "token_pool" in body

    async def test_models_endpoint(self, app_with_mocks):
        """模型列表端点返回已知模型。"""
        r = await app_with_mocks.get("/v1/models")
        assert r.status_code == 200
        body = r.json()
        items = body.get("items", {})
        assert "imagefree" in items
        assert "minimaxh3" in items
        assert "count" in body
        assert body["count"] >= 40

    async def test_stats_endpoint(self, app_with_mocks):
        """统计端点返回完整结构。"""
        r = await app_with_mocks.get("/v1/stats")
        assert r.status_code == 200
        body = r.json()
        assert "total_requests" in body
        assert "total_images" in body
        assert "processing" in body
        assert "daily" in body
        assert "monthly" in body

    async def test_gallery_endpoint(self, app_with_mocks):
        """画廊端点返回 items 和 count。"""
        r = await app_with_mocks.get("/v1/gallery")
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "count" in body