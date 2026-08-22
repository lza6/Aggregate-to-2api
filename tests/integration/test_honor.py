"""集成测试：捐赠页（/v1/honor）+ 首页 footer 捐赠入口。"""
import pytest


@pytest.mark.integration
class TestHonor:
    """捐赠通道端点 + 首页 footer 落地。"""

    async def test_honor_returns_donation_info(self, app_with_mocks):
        """GET /v1/honor 返回捐赠二维码路径与文案。"""
        client = app_with_mocks
        r = await client.get("/v1/honor")
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"
        assert body.get("qr_path") == "/static/zanshang.jpg"
        assert body.get("donate") is not None or "donate" in body or "title" in body
        assert body.get("contact_wx") == "Tf00798"
        assert body.get("title") == "支持听风"

    async def test_index_linked_to_zanshang(self, app_with_mocks):
        """GET / 返回 200 且 footer 已挂捐赠入口。"""
        client = app_with_mocks
        r = await client.get("/")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("text/html")
        assert "zanshang" in r.text or "咖啡" in r.text