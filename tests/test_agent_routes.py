"""tests/test_agent_routes.py — P0-11 补测：agent 子系统 5 个 /v1/agent/* 端点。

补测目的：拉高 api/agent/routes.py 覆盖率（当前 49%，5 个端点 handler 分支未测），
使全量 --cov-fail-under=80 门禁达标（本地实测 79% → 目标 80%+）。

验收：
- GET  /v1/agent/skills       列出 skills（按 scene 分组）+ IF_AGENT_SKILLS_ENABLED=0 回退空
- POST /v1/agent/intent       意图分类（规则命中 + Mock LLM unknown）
- GET  /v1/agent/memory      查询记忆 + MEMORY_CONSOLIDATION_ENABLED=0 返回 enabled=False
- POST /v1/agent/memory/observe  L0 观察写入 + 开关关闭 403
- GET  /v1/agent/health      agent 子系统健康快照（4 开关状态 + 4 表名）
"""

from __future__ import annotations

import os

import pytest

# 公益开放：guard_chat_request 仅 per-IP 频控，不强制 Key（v7.7.1 决策）
# agent 开关全部默认开（见 api/config/__init__.py:230-240）
os.environ.setdefault("IF_AGENT_SKILLS_ENABLED", "1")
os.environ.setdefault("IF_AGENT_INTENT_CLASSIFIER", "1")
os.environ.setdefault("IF_MEMORY_CONSOLIDATION_ENABLED", "1")
os.environ.setdefault("IF_PROVIDER_RISK_TIER", "1")
os.environ.setdefault("IF_CRITIC_AGENT_ENABLED", "1")
os.environ.setdefault("IF_MOCK_UPSTREAM", "1")  # LLM 路径走 Mock，不真实付费
os.environ.setdefault("IF_DB_FILE", "data/test-agent-routes.db")
os.environ.setdefault("IF_ACCOUNT_AUTO", "0")
os.environ.setdefault("IF_MOCK_REGISTER", "1")


@pytest.fixture(scope="module")
def client():
    """TestClient 复用 app 单例（与 test_openapi_contract 同模式）。"""
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as c:
        yield c


# ── GET /v1/agent/skills ───────────────────────────────────────
class TestAgentSkillsEndpoint:
    def test_list_skills_returns_grouped_by_scene(self, client):
        """GET /v1/agent/skills 返回 {items: {scene: [...]}, count: int}。"""
        r = client.get("/v1/agent/skills")
        assert r.status_code == 200, f"skills 端点应 200: {r.status_code} {r.text[:200]}"
        body = r.json()
        assert "items" in body
        assert "count" in body
        assert isinstance(body["items"], dict)
        assert isinstance(body["count"], int)
        assert body["count"] >= 0
        # v8.1 已落地三场景：image_quality/prompt_refine/critic
        if body["count"] > 0:
            for scene, skills in body["items"].items():
                assert isinstance(scene, str)
                assert isinstance(skills, list)
                for s in skills:
                    assert "name" in s
                    assert "description" in s
                    assert s["scene"] == scene

    def test_list_skills_when_empty_returns_zero(self, client, monkeypatch):
        """skills 索引为空时（模拟未启用/无 skill 目录）端点回退 count=0 + items={}。

        routes.py:46 调 skill_index.all()；_is_stale 对空 records 会触发 refresh 重扫真实
        目录，故直接 monkeypatch all() 方法返回空 list 模拟"无 skill"场景。
        """
        from api.skills import loader

        monkeypatch.setattr(loader.skill_index, "all", lambda: [])
        r = client.get("/v1/agent/skills")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 0
        assert body["items"] == {}


# ── POST /v1/agent/intent ───────────────────────────────────────
class TestAgentIntentEndpoint:
    def test_classify_intent_rule_hit(self, client):
        """POST /v1/agent/intent 画图意图命中规则，不触发 LLM。"""
        r = client.post("/v1/agent/intent", json={"prompt": "帮我画一张猫的图"})
        assert r.status_code == 200, f"intent 端点应 200: {r.status_code} {r.text[:200]}"
        body = r.json()
        assert body["scene"] == "image"
        assert body["provider_hint"] == "imagefree"
        assert body["confidence"] >= 0.6
        assert body["llm_used"] is False

    def test_classify_intent_llm_mock_unknown(self, client):
        """模糊意图走 LLM Mock（IF_MOCK_UPSTREAM=1），返回 unknown + 低 confidence + llm_used=True。"""
        r = client.post("/v1/agent/intent", json={"prompt": "随便来点啥"})
        assert r.status_code == 200
        body = r.json()
        assert body["llm_used"] is True
        assert body["confidence"] < 0.6
        assert body["scene"] == "unknown"

    def test_classify_intent_empty_prompt_rejected(self, client):
        """空 prompt 触发 pydantic 校验 422（IntentRequest min_length=1）。"""
        r = client.post("/v1/agent/intent", json={"prompt": ""})
        assert r.status_code == 422


# ── GET /v1/agent/memory ────────────────────────────────────────
class TestAgentMemoryQueryEndpoint:
    def test_query_memory_returns_records_or_empty(self, client):
        """GET /v1/agent/memory 返回 {items: [...], count: int, enabled: bool}。"""
        r = client.get("/v1/agent/memory?scene=image&layer=L1&limit=10")
        assert r.status_code == 200, f"memory 端点应 200: {r.status_code} {r.text[:200]}"
        body = r.json()
        assert "items" in body
        assert "count" in body
        assert "enabled" in body
        assert body["enabled"] is True
        assert isinstance(body["items"], list)
        assert isinstance(body["count"], int)

    def test_query_memory_when_disabled_returns_empty(self, client, monkeypatch):
        """MEMORY_CONSOLIDATION_ENABLED=0 时返回 enabled=False + 空列表。"""
        from api.agent import memory

        monkeypatch.setattr(memory, "MEMORY_CONSOLIDATION_ENABLED", False)
        r = client.get("/v1/agent/memory")
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is False
        assert body["count"] == 0
        assert body["items"] == []


# ── POST /v1/agent/memory/observe ──────────────────────────────
class TestAgentMemoryObserveEndpoint:
    def test_observe_writes_l0_record(self, client):
        """POST /v1/agent/memory/observe 写入 L0 观察记录，返回 id + stored=True。"""
        r = client.post(
            "/v1/agent/memory/observe",
            json={
                "user_key": "test-user",
                "scene": "image",
                "content": "用户偏好赛博朋克风格",
                "importance": 0.8,
            },
        )
        assert r.status_code == 200, f"observe 端点应 200: {r.status_code} {r.text[:200]}"
        body = r.json()
        assert body["stored"] is True
        assert isinstance(body["id"], int)
        assert body["id"] > 0

    def test_observe_when_disabled_returns_403(self, client, monkeypatch):
        """MEMORY_CONSOLIDATION_ENABLED=0 时 observe 返回 403 FORBIDDEN。"""
        from api.agent import memory

        monkeypatch.setattr(memory, "MEMORY_CONSOLIDATION_ENABLED", False)
        r = client.post(
            "/v1/agent/memory/observe",
            json={"scene": "image", "content": "test", "importance": 0.5},
        )
        assert r.status_code == 403
        body = r.json()
        assert "error" in body

    def test_observe_invalid_importance_rejected(self, client):
        """importance 超出 [0.0, 1.0] 触发 422。"""
        r = client.post(
            "/v1/agent/memory/observe",
            json={"scene": "image", "content": "test", "importance": 1.5},
        )
        assert r.status_code == 422


# ── GET /v1/agent/health ────────────────────────────────────────
class TestAgentHealthEndpoint:
    def test_health_returns_all_switches(self, client):
        """GET /v1/agent/health 返回 4 开关状态 + 4 表名映射。"""
        r = client.get("/v1/agent/health")
        assert r.status_code == 200, f"health 端点应 200: {r.status_code} {r.text[:200]}"
        body = r.json()
        assert "intent_classifier" in body
        assert "memory_consolidation" in body
        assert "provider_risk_tier" in body
        assert isinstance(body["intent_classifier"], bool)
        assert isinstance(body["memory_consolidation"], bool)
        assert isinstance(body["provider_risk_tier"], bool)
        # 4 表名映射
        tables = body["memory_tables"]
        assert tables["L0"] == "mem_observations"
        assert tables["L1"] == "mem_atoms"
        assert tables["L2"] == "mem_scenarios"
        assert tables["L3"] == "mem_persona"
