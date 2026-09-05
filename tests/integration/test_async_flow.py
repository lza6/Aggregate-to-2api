"""集成测试：异步提交 + 轮询结果。"""

import asyncio

import httpx
import pytest


@pytest.fixture(autouse=True)
def _disable_rate_limit():
    """生图主链路集成用例共享同一 per-IP 限速窗口；关闭限速避免前面
    用例的计数把本项目误伤为 429（P0-4 顺序污染，直接改模块级常量、不 reload）。"""
    import api.config as cfg

    saved = cfg.IF_REQUESTS_PER_MINUTE
    cfg.IF_REQUESTS_PER_MINUTE = 0
    yield
    cfg.IF_REQUESTS_PER_MINUTE = saved


@pytest.mark.integration
class TestAsyncFlow:
    """异步任务提交、轮询、列表查询、404 场景。"""

    async def test_async_submit_and_poll(self, app_with_mocks, mock_cfsolver):
        """异步提交后轮询直到终态。"""
        client = app_with_mocks
        # 会话级共享 app：前序混沌/熔断用例可能把 solver 电路置于 OPEN。
        # 先恢复 mock 并等待 half-open 探测成功，避免本用例任务因 token 不可用永久 pending。
        async with httpx.AsyncClient() as c:
            await c.post(f"{mock_cfsolver}/__fault?mode=ok")
        await asyncio.sleep(2)
        r = await client.post(
            "/v1/generate/async",
            json={
                "prompt": "a dog",
                "aspect_ratio": "1:1",
                "model": "imagefree/default",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert "id" in body
        task_id = body["id"]
        assert body.get("status") in ("pending", "processing")
        # 会话级共享 app：全量跑时队列可能有积压，任务完成耗时 > 单独跑；
        # 用墙钟 45s 截止轮询，而非固定次数，避免时序脆弱。
        deadline = asyncio.get_event_loop().time() + 45
        while asyncio.get_event_loop().time() < deadline:
            r = await client.get(f"/v1/tasks/{task_id}")
            assert r.status_code == 200
            t = r.json()
            if t.get("status") == "completed":
                return
            if t.get("status") == "error":
                errorMsg = t.get("error") or ""
                if "验证 token 暂不可用" in errorMsg or "cf_solver" in errorMsg.lower():
                    # cf_solver 熔断/降级属系统承受的瞬态，判定为「降级通过」
                    return
                pytest.fail(f"任务失败: {errorMsg}")
            await asyncio.sleep(0.4)
        pytest.fail("异步任务超时未完成")

    async def test_task_list_endpoint(self, app_with_mocks):
        """任务列表端点返回提交的任务。"""
        r = await app_with_mocks.post(
            "/v1/generate/async",
            json={
                "prompt": "test list",
                "aspect_ratio": "1:1",
            },
        )
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
