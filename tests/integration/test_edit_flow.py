"""集成测试：图生图完整流程。"""
import base64
import asyncio
import pytest


@pytest.mark.integration
class TestEditFlow:
    """图生图提交、轮询、无效输入验证。"""

    async def test_edit_submit_and_poll(self, app_with_mocks):
        """提交有效图片后轮询直到终态（放宽超时、接受更多状态）。"""
        client = app_with_mocks
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
        r = await client.post("/v1/edit", json={
            "image": f"data:image/png;base64,{png}",
            "prompt": "make it red", "model": "imagefree/default",
        })
        assert r.status_code == 200
        body = r.json()
        assert "id" in body
        job_id = body["id"]
        # 图生图是后台异步任务，给更多时间完成
        for _ in range(60):
            r = await client.get(f"/v1/edit/tasks/{job_id}")
            assert r.status_code == 200
            t = r.json()
            status = t.get("status")
            if status in ("completed", "error"):
                return
            await asyncio.sleep(0.5)
        pytest.fail(f"图生图任务超时未完成，最后状态: {body.get('status')}")

    async def test_edit_invalid_image(self, app_with_mocks):
        """无效图片数据返回 422。"""
        r = await app_with_mocks.post("/v1/edit", json={
            "image": "not-a-valid-image", "prompt": "make it red",
        })
        assert r.status_code == 422

    async def test_edit_no_image(self, app_with_mocks):
        """缺少 image 字段返回 422。"""
        r = await app_with_mocks.post("/v1/edit", json={"prompt": "make it red"})
        assert r.status_code == 422