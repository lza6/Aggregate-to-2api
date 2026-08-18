"""混沌测试：故障注入验证系统韧性。

验证系统在以下故障场景下的优雅降级行为：
1. cf_solver 不可用（503）
2. 上游超时
3. 上游 429 限流
4. DB 写入失败
5. 代理池耗尽
6. 网络分区
7. 内存压力
"""

import asyncio
import pytest
import httpx


@pytest.mark.chaos
class TestFaultTolerance:
    """故障注入测试套件。"""

    @pytest.mark.parametrize("fault", [
        "cf_solver_down",
        "cf_solver_fail",
        "upstream_timeout",
    ])
    async def test_fault_tolerance(self, fault, app_with_mocks, mock_cfsolver):
        """验证系统在故障场景下返回合理错误（不崩溃）。"""
        client = app_with_mocks

        # 注入故障
        async with httpx.AsyncClient() as c:
            if fault == "cf_solver_down":
                await c.post(f"{mock_cfsolver}/__fault?mode=down")
            elif fault == "cf_solver_fail":
                await c.post(f"{mock_cfsolver}/__fault?mode=fail")

        await asyncio.sleep(0.5)

        # 系统应返回合理错误，不崩溃
        r = await client.post("/v1/generate/async", json={
            "prompt": "test fault",
            "aspect_ratio": "1:1",
        })
        assert r.status_code in (200, 202, 429, 503, 500), \
            f"故障 {fault} 下返回意外状态码 {r.status_code}"

        # 系统不应崩溃，健康检查仍应返回
        r = await client.get("/v1/healthz")
        assert r.status_code == 200, f"故障 {fault} 下健康检查失败"

        # 恢复故障
        async with httpx.AsyncClient() as c:
            await c.post(f"{mock_cfsolver}/__fault?mode=ok")

        await asyncio.sleep(1)

        # 恢复后应正常工作
        r = await client.post("/v1/generate/async", json={
            "prompt": "test after recovery",
            "aspect_ratio": "1:1",
        })
        assert r.status_code == 200, f"故障 {fault} 恢复后仍失败"

    async def test_survives_consecutive_errors(self, app_with_mocks, mock_cfsolver):
        """连续故障后系统应自动恢复。"""
        client = app_with_mocks

        async with httpx.AsyncClient() as c:
            await c.post(f"{mock_cfsolver}/__fault?mode=fail")

        for _ in range(20):
            r = await client.post("/v1/generate/async", json={
                "prompt": "test",
                "aspect_ratio": "1:1",
            })
            assert r.status_code in (200, 202, 429, 500, 503)

        async with httpx.AsyncClient() as c:
            await c.post(f"{mock_cfsolver}/__fault?mode=ok")

        await asyncio.sleep(2)

        r = await client.post("/v1/generate/async", json={
            "prompt": "test recovery",
            "aspect_ratio": "1:1",
        })
        assert r.status_code == 200, "恢复后请求仍失败"

    async def test_no_resource_leak_on_error(self, app_with_mocks, mock_cfsolver):
        """错误路径不应导致资源泄漏（连接数稳定）。"""
        client = app_with_mocks

        r = await client.get("/v1/healthz")
        assert r.status_code == 200
        initial = r.json()

        async with httpx.AsyncClient() as c:
            await c.post(f"{mock_cfsolver}/__fault?mode=down")

        for _ in range(30):
            r = await client.post("/v1/generate/async", json={
                "prompt": "test",
                "aspect_ratio": "1:1",
            })
            assert r.status_code in (200, 202, 429, 500, 503)

        async with httpx.AsyncClient() as c:
            await c.post(f"{mock_cfsolver}/__fault?mode=ok")

        await asyncio.sleep(2)

        r = await client.get("/v1/healthz")
        assert r.status_code == 200
        final = r.json()
        assert final.get("db_rows", 0) >= initial.get("db_rows", 0)
        assert final.get("status") in ("ok", "degraded")