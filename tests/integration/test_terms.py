"""集成测试：S-15 服务条款细分页面 + S-5 慢请求静态看板。"""
import pytest


@pytest.mark.integration
class TestTerms:
    """服务条款细分页面（S-15）。"""

    SUB_SLUGS = ("service", "privacy", "content", "disclaimer")

    async def test_overview_page(self, app_with_mocks):
        """总览 /v1/terms 返回 200 且为 HTML。"""
        r = await app_with_mocks.get("/v1/terms")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

    async def test_sub_pages_ok(self, app_with_mocks):
        """4 个子条款页均 200 且 body 含非空 <title>。"""
        for slug in self.SUB_SLUGS:
            r = await app_with_mocks.get(f"/v1/terms/{slug}")
            assert r.status_code == 200, f"/v1/terms/{slug} 期望 200"
            body = r.text
            assert "<title>" in body
            title = body.split("<title>", 1)[1].split("</title>", 1)[0]
            assert title.strip(), f"/v1/terms/{slug} 的 <title> 为空"

    async def test_terms_index(self, app_with_mocks):
        """/v1/terms/index 返回结构化列表，含 4 项且字段齐全。"""
        r = await app_with_mocks.get("/v1/terms/index")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 4
        slugs = {item["slug"] for item in data}
        assert slugs == set(self.SUB_SLUGS)
        for item in data:
            assert item["title"]
            assert item["url"].startswith("/v1/terms/")

    async def test_sub_unknown_404(self, app_with_mocks):
        """未知子页面返回 404，且错误码为 NOT_FOUND。"""
        r = await app_with_mocks.get("/v1/terms/nonexistent")
        assert r.status_code == 404
        body = r.json()
        assert body["error"]["code"] == "SYS.003"


@pytest.mark.integration
class TestSlowView:
    """S-5: 慢请求静态看板。"""

    async def test_slow_view_ok(self, app_with_mocks):
        """/v1/slow/view 返回 200 且 content-type 为 text/html。"""
        r = await app_with_mocks.get("/v1/slow/view")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

    async def test_slow_view_has_dashboard_markers(self, app_with_mocks):
        """看板包含刷新按钮与轮询逻辑。"""
        r = await app_with_mocks.get("/v1/slow/view")
        body = r.text
        assert "refresh-btn" in body
        assert "15000" in body  # 15s 自动轮询