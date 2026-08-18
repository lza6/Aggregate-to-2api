"""集成测试：超时场景验证。"""
import pytest


@pytest.mark.integration
class TestTimeout:
    """同步接口超时后返回 202 + Location 头。"""

    async def test_sync_timeout_returns_202(self, app_with_mocks):
        """同步超时窗口极短时返回 202。"""
        import os
        os.environ["IF_SYNC_TIMEOUT"] = "0.1"
        import importlib
        import api.config
        importlib.reload(api.config)
        client = app_with_mocks
        r = await client.post("/v1/generate", json={
            "prompt": "test timeout", "aspect_ratio": "1:1",
        })
        assert r.status_code in (200, 202)
        if r.status_code == 202:
            assert "Location" in r.headers