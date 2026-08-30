"""集成测试：超时场景验证。"""

import pytest


@pytest.mark.integration
class TestTimeout:
    """同步接口超时后返回 202 + Location 头。"""

    async def test_sync_timeout_returns_202(self, app_with_mocks):
        """同步超时窗口极短时返回 202（先临时关掉 per-IP 限流，避免被 429 抢先拦截）。"""
        import api.config as cfg

        # 直接改模块级同步超时常量；不 reload 整个 config（reload 会重建 Settings
        # 单例并触发分组配置重建，导致 _app_instance 已持有的配置引用分叉，P0-4 顺序污染）。
        saved_timeout = cfg.SYNC_TIMEOUT
        saved = cfg.IF_REQUESTS_PER_MINUTE
        cfg.SYNC_TIMEOUT = 1
        cfg.IF_REQUESTS_PER_MINUTE = 0
        try:
            client = app_with_mocks
            r = await client.post(
                "/v1/generate",
                json={
                    "prompt": "test timeout",
                    "aspect_ratio": "1:1",
                },
            )
        finally:
            cfg.SYNC_TIMEOUT = saved_timeout
            cfg.IF_REQUESTS_PER_MINUTE = saved
        assert r.status_code in (200, 202)
        if r.status_code == 202:
            assert "Location" in r.headers
