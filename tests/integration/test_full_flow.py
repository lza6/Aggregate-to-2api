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
        # P15: 新增段
        assert "providers" in body
        assert set(body["providers"]) >= {"imagefree", "aifreeforever", "nanobanana"}
        for p in body["providers"].values():
            assert "status" in p and "last_check" in p
        assert "queue" in body
        assert set(body["queue"]) >= {"admin", "high", "normal", "limits"}
        assert body["queue"]["limits"]["admin"] == 200
        assert "log_dir" in body
        assert "path" in body["log_dir"] and "writable" in body["log_dir"]

    async def test_models_endpoint(self, app_with_mocks):
        """模型列表端点返回已知模型。"""
        r = await app_with_mocks.get("/v1/models")
        assert r.status_code == 200
        body = r.json()
        items = body.get("items", {})
        assert "imagefree" in items
        assert "nanobanana" in items
        assert "count" in body
        assert body["count"] >= 30

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
        # P3-2: GC 可观测闭环
        assert "base64_gc" in body
        gc = body["base64_gc"]
        for k in ("total_files", "hot_files", "cold_files",
                  "pending_cleanup_count", "quota_gb", "usage_pct"):
            assert k in gc, f"base64_gc 缺少字段 {k}"

    async def test_gallery_endpoint(self, app_with_mocks):
        """画廊端点返回 items 和 count。"""
        r = await app_with_mocks.get("/v1/gallery")
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "count" in body

@pytest.mark.integration
class TestIdempotencyFlow:
    """P-TEST-A8: 幂等 key 集成链路（conftest 已设 IF_IDEMPOTENCY_ENABLED=1）。"""

    async def test_same_key_returns_same_task(self, app_with_mocks):
        payload = {"prompt": "a cat", "aspect_ratio": "1:1",
                   "model": "imagefree/default", "idempotency_key": "itg-key-001"}
        r1 = await app_with_mocks.post("/v1/generate/async", json=payload)
        assert r1.status_code == 200
        r2 = await app_with_mocks.post("/v1/generate/async", json=payload)
        assert r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]

    async def test_different_key_different_task(self, app_with_mocks):
        r1 = await app_with_mocks.post("/v1/generate/async", json={
            "prompt": "a cat", "aspect_ratio": "1:1", "model": "imagefree/default",
            "idempotency_key": "itg-key-a"})
        r2 = await app_with_mocks.post("/v1/generate/async", json={
            "prompt": "a cat", "aspect_ratio": "1:1", "model": "imagefree/default",
            "idempotency_key": "itg-key-b"})
        assert r1.json()["id"] != r2.json()["id"]
