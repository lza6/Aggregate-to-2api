"""集成测试：熔断器行为验证。"""
import pytest
import httpx
import asyncio


@pytest.mark.integration
class TestCircuitBreaker:
    """solver 熔断器 OPEN→HALF-OPEN→CLOSED 生命周期。"""

    async def test_solver_circuit_breaker(self, app_with_mocks, mock_cfsolver):
        """连续失败触发熔断，恢复后重新可用。"""
        import api.config as cfg
        client = app_with_mocks
        # 临时关掉 per-IP 限流，避免循环提交被 429 抢先拦截而熔断阈值不触发
        saved = cfg.IF_REQUESTS_PER_MINUTE
        cfg.IF_REQUESTS_PER_MINUTE = 0
        try:
            # 注入故障
            async with httpx.AsyncClient() as c:
                await c.post(f"{mock_cfsolver}/__fault?mode=fail")
            # 触发连续失败达到熔断阈值
            for _ in range(10):
                await client.post("/v1/generate/async", json={
                    "prompt": "test", "aspect_ratio": "1:1",
                })
            # 恢复 mock
            async with httpx.AsyncClient() as c:
                await c.post(f"{mock_cfsolver}/__fault?mode=ok")
            # 等待 half-open 探测 + 恢复
            await asyncio.sleep(2)
            r = await client.post("/v1/generate/async", json={
                "prompt": "test after recovery", "aspect_ratio": "1:1",
            })
        finally:
            cfg.IF_REQUESTS_PER_MINUTE = saved
        assert r.status_code == 200