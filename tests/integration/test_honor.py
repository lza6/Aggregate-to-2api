"""集成测试：捐赠页（/v1/honor）+ 首页 footer 捐赠入口。"""
import pytest


@pytest.mark.integration
class TestHonor:
    """捐赠通道端点 + 首页 footer 落地。"""

    async def test_honor_returns_donation_page(self, app_with_mocks):
        """GET /v1/honor 返回渲染好的独立 HTML 页面。"""
        client = app_with_mocks
        r = await client.get("/v1/honor")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("text/html")
        assert "支持听风AI" in r.text
        assert "/static/zanshang.jpg" in r.text

    async def test_honor_data_returns_json(self, app_with_mocks):
        """GET /v1/honor/data 返回 JSON 数据。"""
        client = app_with_mocks
        r = await client.get("/v1/honor/data")
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"
        assert body.get("qr_path") == "/static/zanshang.jpg"
        assert body.get("contact_wx") == "Tf00798"
        assert body.get("title") == "支持听风"

    async def test_index_linked_to_zanshang(self, app_with_mocks):
        """GET / 返回 200 且为 Vue3 公开落地页（SPA shell 由 JS 挂载）。"""
        client = app_with_mocks
        r = await client.get("/")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("text/html")
        # v6.5.0：公开首页改为 Vue3 落地页（引导至 /admin、/docs、/v1/honor 捐赠页）。
        # / 现在返回 SPA 壳（<div id="app"> + /assets/* 脚本），内容由 JS 渲染，不再内联单文件 docs.html。
        assert 'id="app"' in r.text
        assert "/assets/" in r.text