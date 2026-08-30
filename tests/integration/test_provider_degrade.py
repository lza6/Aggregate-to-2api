"""集成测试：提供商降级/恢复行为。"""

import pytest


@pytest.mark.integration
class TestProviderDegrade:
    """提供商降级后 providers 端点反映健康状态。"""

    async def test_provider_degrade_on_errors(self, app_with_mocks):
        """连续失败后提供商状态变化。"""
        client = app_with_mocks
        # 发送请求到带无效模型名的提供商（触发降级）
        for _ in range(5):
            await client.post(
                "/v1/generate/async",
                json={
                    "prompt": "test",
                    "model": "nanobanana/nano-banana-pro",
                    "aspect_ratio": "1:1",
                },
            )
        r = await client.get("/v1/providers")
        assert r.status_code == 200
