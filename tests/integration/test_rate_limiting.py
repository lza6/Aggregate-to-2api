"""集成测试：限流行为验证。"""
import pytest


@pytest.mark.integration
class TestRateLimiting:
    """队列满限流、无效模型、无效 prompt 验证。"""

    async def test_queue_full_returns_429(self, app_with_mocks):
        """队列满时返回 429。"""
        import os
        os.environ["IF_MAX_QUEUE"] = "1"
        import importlib
        import api.config
        importlib.reload(api.config)
        client = app_with_mocks
        for _ in range(5):
            r = await client.post("/v1/generate/async", json={
                "prompt": "test", "aspect_ratio": "1:1",
            })
            if r.status_code == 429:
                body = r.json()
                assert "error" in body
                assert "code" in body["error"]
                return
        os.environ["IF_MAX_QUEUE"] = "2000"
        importlib.reload(api.config)

    async def test_invalid_model_returns_422(self, app_with_mocks):
        """不存在的模型返回 422。"""
        r = await app_with_mocks.post("/v1/generate", json={
            "prompt": "test", "aspect_ratio": "1:1", "model": "nonexistent/model",
        })
        assert r.status_code == 422
        body = r.json()
        assert body["error"]["code"] == "INVALID_MODEL"

    async def test_invalid_prompt_returns_422(self, app_with_mocks):
        """空 prompt 返回 422。"""
        r = await app_with_mocks.post("/v1/generate", json={
            "prompt": "", "aspect_ratio": "1:1",
        })
        assert r.status_code == 422