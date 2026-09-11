"""tests/test_agent_skills_routes.py — v12.0.0 P1-M5 技能可发现性端点测试（TDD）。

覆盖（对齐 api/agent/routes.py 现有契约）：
- GET /v1/agent/skills 按 scene 分组返回（items={scene:[...]}, count=N）
- P1-M5 新增场景技能（ecommerce/ppt）可被发现
- GET /v1/agent/skills/{name} 单技能详情（v12.0.0 新增，含 body 预览）
- 未知技能 → 404（AppError 信封 {"error":{"code","message"}}）
- IF_AGENT_SKILLS_ENABLED=0 → 404（v12.0.0 补齐的开关）
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """skills 端点专用 TestClient（app 已由 conftest lifespan 装配）。"""
    from api.main import app

    with TestClient(app) as c:
        yield c


class TestSkillsList:
    def test_list_returns_scene_grouped_items(self, client: TestClient):
        """清单按 scene 分组：items={scene:[{name,description,scene}]} + count。"""
        resp = client.get("/v1/agent/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data and "count" in data
        assert isinstance(data["items"], dict)  # scene 分组
        total = sum(len(v) for v in data["items"].values())
        assert data["count"] == total
        assert total >= 3  # critic/image_quality/prompt_refine 内置

    def test_list_contains_new_scene_skills(self, client: TestClient):
        """P1-M5：新建电商/PPT 场景技能可被发现。"""
        resp = client.get("/v1/agent/skills")
        data = resp.json()
        names = {item["name"] for group in data["items"].values() for item in group}
        assert "ecommerce-visual-copywriting" in names
        assert "ppt-outline-gen" in names
        assert "ecommerce" in data["items"]
        assert "ppt" in data["items"]

    def test_list_item_shape(self, client: TestClient):
        """每条记录含 name/description/scene 三键（frontmatter 可发现性契约）。"""
        resp = client.get("/v1/agent/skills")
        item = next(iter(next(iter(resp.json()["items"].values()))))
        assert set(item.keys()) == {"name", "description", "scene"}


class TestSkillsGet:
    def test_get_known_skill_returns_body(self, client: TestClient):
        """v12.0.0 新增单技能详情：name/scene/body 预览。"""
        resp = client.get("/v1/agent/skills/ecommerce-visual-copywriting")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "ecommerce-visual-copywriting"
        assert data["scene"] == "ecommerce"
        assert "转化驱动力" in data["body"]  # body 预览含核心节
        assert data["path"].endswith("SKILL.md")

    def test_get_unknown_skill_404_envelope(self, client: TestClient):
        """未知技能 → 404（AppError 信封 {"error":{"code","message"}}）。"""
        resp = client.get("/v1/agent/skills/no-such-skill-xyz")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        assert "技能不存在" in body["error"]["message"]


class TestSkillsSwitch:
    def test_disabled_switch_404(self, client: TestClient, monkeypatch):
        """IF_AGENT_SKILLS_ENABLED=0 → 404（v12.0.0 补齐的 config 工厂开关）。"""
        from api.config import reset_settings

        monkeypatch.setenv("IF_AGENT_SKILLS_ENABLED", "0")
        reset_settings()
        try:
            resp = client.get("/v1/agent/skills")
            assert resp.status_code == 404
            resp2 = client.get("/v1/agent/skills/ecommerce-visual-copywriting")
            assert resp2.status_code == 404
        finally:
            monkeypatch.setenv("IF_AGENT_SKILLS_ENABLED", "1")
            reset_settings()
