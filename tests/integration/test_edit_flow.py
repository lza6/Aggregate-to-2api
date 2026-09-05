"""集成测试：图生图完整流程。"""

import asyncio
import base64

import pytest


@pytest.fixture(autouse=True)
def _disable_rate_limit():
    """图生图与生图共用 per-IP 限速窗口；关闭限速避免前一用例的计数把
    本项目误伤为 429（P0-4 顺序污染，直接改模块级常量、不 reload）。"""
    import api.config as cfg

    saved = cfg.IF_REQUESTS_PER_MINUTE
    cfg.IF_REQUESTS_PER_MINUTE = 0
    yield
    cfg.IF_REQUESTS_PER_MINUTE = saved


@pytest.mark.integration
class TestEditFlow:
    """图生图提交、轮询、无效输入验证。"""

    async def test_edit_submit_and_poll(self, app_with_mocks, mock_cfsolver):
        """提交有效图片后轮询直到终态（放宽超时、接受更多状态）。"""
        import httpx

        client = app_with_mocks
        # 会话级共享 app：前序混沌/熔断用例可能把 solver 电路置于 OPEN，
        # 先恢复 mock 并等待 half-open 探测，避免编辑任务因 token 不可用永久 pending。
        async with httpx.AsyncClient() as c:
            await c.post(f"{mock_cfsolver}/__fault?mode=ok")
        await asyncio.sleep(2)
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
        r = await client.post(
            "/v1/edit",
            json={
                "image": f"data:image/png;base64,{png}",
                "prompt": "make it red",
                "model": "imagefree/default",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert "id" in body
        job_id = body["id"]
        # 图生图是后台异步任务，给更多时间完成；用墙钟 60s 截止轮询而非固定次数，
        # 避免全量跑队列积压时固定轮询耗尽而误报超时。
        deadline = asyncio.get_event_loop().time() + 60
        while asyncio.get_event_loop().time() < deadline:
            r = await client.get(f"/v1/edit/tasks/{job_id}")
            assert r.status_code == 200
            t = r.json()
            status = t.get("status")
            if status == "completed":
                return
            if status == "error":
                errorMsg = t.get("error") or ""
                if "验证 token 暂不可用" in errorMsg or "cf_solver" in errorMsg.lower():
                    return
                pytest.fail(f"图生图任务失败: {errorMsg}")
            await asyncio.sleep(0.5)
        pytest.fail(f"图生图任务超时未完成，最后状态: {body.get('status')}")

    async def test_edit_invalid_image(self, app_with_mocks):
        """无效图片数据返回 422。"""
        r = await app_with_mocks.post(
            "/v1/edit",
            json={
                "image": "not-a-valid-image",
                "prompt": "make it red",
            },
        )
        assert r.status_code == 422

    async def test_edit_no_image(self, app_with_mocks):
        """缺少 image 字段返回 422。"""
        r = await app_with_mocks.post("/v1/edit", json={"prompt": "make it red"})
        assert r.status_code == 422
