"""集成测试：限流行为验证。"""
import pytest


@pytest.mark.integration
class TestRateLimiting:
    """队列满限流、无效模型、无效 prompt 验证。"""

    async def test_queue_full_returns_429(self, app_with_mocks):
        """队列满时返回 429。"""
        import api.config as cfg
        saved = cfg.MAX_QUEUE
        # 直接改模块级队列上限常量；不 reload 整个 config（避免 Settings 单例/
        # 分组配置重建导致 _app_instance 持有的引用分叉，P0-4 顺序污染）。
        cfg.MAX_QUEUE = 1
        client = app_with_mocks
        try:
            for _ in range(5):
                r = await client.post("/v1/generate/async", json={
                    "prompt": "test", "aspect_ratio": "1:1",
                })
                if r.status_code == 429:
                    body = r.json()
                    assert "error" in body
                    assert "code" in body["error"]
                    return
        finally:
            cfg.MAX_QUEUE = saved

    async def test_invalid_model_returns_422(self, app_with_mocks):
        """不存在的模型返回 422（先临时关掉 per-IP 限流，避免该请求被 429 抢先拦截）。"""
        import api.config as cfg
        saved = cfg.IF_REQUESTS_PER_MINUTE
        # 直接改模块级限流常量，避免 reload 破坏 Settings 单例/分组配置（P0-4 顺序污染）
        cfg.IF_REQUESTS_PER_MINUTE = 0
        try:
            r = await app_with_mocks.post("/v1/generate", json={
                "prompt": "test", "aspect_ratio": "1:1", "model": "nonexistent/model",
            })
        finally:
            cfg.IF_REQUESTS_PER_MINUTE = saved
        assert r.status_code == 422
        body = r.json()
        assert "VAL" in body["error"]["code"] or "INVALID_MODEL" in body["error"]["code"]

    async def test_invalid_prompt_returns_422(self, app_with_mocks):
        """空 prompt 返回 422。"""
        r = await app_with_mocks.post("/v1/generate", json={
            "prompt": "", "aspect_ratio": "1:1",
        })
        assert r.status_code == 422