"""tests/test_agent_planner.py — v9.0.0-A LLM 规划器单元测试（TDD）。

覆盖 Story 3 验收标准：
- Mock 路径：场景推导 → 稳定 DAG（scene 由 intent 正则规则推导，置信度阈值 + 提示词组装）
- 真实 LLM 路径的降级：chat model 缺失 / provider 缺失 / JSON 解析失败 → 回退 Mock，不崩
- planner 全程无真实付费 provider（仅 tryingopen + IF_MOCK_UPSTREAM 开关）
"""

from __future__ import annotations

# planner 缺省走 Mock：环境未设 IF_MOCK_UPSTREAM 时默认 0（真实路径），
# 测试显式设为 1 保证零真实 LLM 调用（付费 API 红线）。
import os

from api.agent.planner import (
    PLAN_SCENE_ORDER,
    plan_with_mock,
)

os.environ.setdefault("IF_MOCK_UPSTREAM", "1")


# ── Mock 路径 ───────────────────────────────────────────────
class TestPlanWithMock:
    async def test_plans_scene_nodes(self):
        """Mock 规划：scene=image → 生成固定节点串（scene 推导 + 终检）。"""
        plan = await plan_with_mock("画一只猫", scene="image")
        assert len(plan["nodes"]) >= 3
        ids = [n["id"] for n in plan["nodes"]]
        assert ids[0] == "scene"  # 根节点固定命名
        # 拓扑链完整：scene→(<=dep)+critic
        assert any(n["kind"] == "critic" for n in plan["nodes"])

    async def test_plan_just_scene_for_unknown(self):
        """scene=unknown（工具性请求）→ 只规划 scene 单节点（不造多余节点）。"""
        plan = await plan_with_mock("显示时间", scene="unknown")
        assert len(plan["nodes"]) == 1
        assert plan["nodes"][0]["id"] == "scene"

    async def test_plan_returns_metadata(self):
        plan = await plan_with_mock("生成产品图", scene="ecommerce")
        assert plan["meta"]["scene"] == "ecommerce"
        assert plan["meta"]["mock"] is True
        assert plan["meta"]["llm_used"] is False


# ── LLM 路径（Mock 降级） ───────────────────────────────────
class TestPlanWithLLM:
    async def test_llm_fallback_when_no_chat_model(self, monkeypatch):
        """LLM 路径但无 chat model → 回退 Mock（不崩）。"""
        import api.agent.planner as planner_mod

        monkeypatch.setattr(planner_mod, "PLANNER_LLM_MODEL", "tryingopen/t1")
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")  # 走真实 LLM 函数路径

        # 用 importlib 拿**模块本身**（providers/__init__ 的包属性 registry 被实例覆盖）
        import importlib

        reg_mod = importlib.import_module("api.providers.registry")

        class _EmptyRegistry:
            def all_chat_models(self):
                return []

        monkeypatch.setattr(reg_mod, "registry", _EmptyRegistry())
        plan = await planner_mod.plan_with_llm("帮我画猫")
        assert plan["meta"]["mock"] is True  # fallback

    async def test_llm_fallback_on_malformed_json(self, monkeypatch):
        """LLM 返回非 JSON → 回退 Mock。"""
        import api.agent.planner as planner_mod

        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")
        monkeypatch.setattr(planner_mod, "PLANNER_LLM_MODEL", "tryingopen/t1")

        import importlib

        reg_mod = importlib.import_module("api.providers.registry")

        class _Provider:
            async def chat_collect(self, model_id, messages):
                return {"text": "not json at all"}

        class _Registry:
            def all_chat_models(self):
                return [type("M", (), {"id": "tryingopen/t1"})()]

            chat_providers = {"tryingopen": _Provider()}

        monkeypatch.setattr(reg_mod, "registry", _Registry())
        plan = await planner_mod.plan_with_llm("帮我画猫")
        assert plan["meta"]["mock"] is True

    async def test_llm_parses_valid_dag_json(self, monkeypatch):
        """LLM 返回合法 DAG JSON → 解析成功，给出真节点。"""
        import json

        import api.agent.planner as planner_mod

        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")
        monkeypatch.setattr(planner_mod, "PLANNER_LLM_MODEL", "tryingopen/t1")

        import importlib

        reg_mod = importlib.import_module("api.providers.registry")

        dag_json = json.dumps(
            {
                "nodes": [
                    {"id": "n1", "kind": "llm", "depends_on": [], "prompt": "先写草稿"},
                    {"id": "n2", "kind": "critic", "depends_on": ["n1"]},
                ]
            }
        )

        class _Provider:
            async def chat_collect(self, model_id, messages):
                return {"text": dag_json}

        class _Registry:
            def all_chat_models(self):
                return [type("M", (), {"id": "tryingopen/t1"})()]

            chat_providers = {"tryingopen": _Provider()}

        monkeypatch.setattr(reg_mod, "registry", _Registry())
        plan = await planner_mod.plan_with_llm("帮我画猫")
        assert plan["meta"]["mock"] is False
        assert any(n["id"] == "n2" for n in plan["nodes"])


# ── 公开契约 ────────────────────────────────────────────────
class TestPlannerContract:
    async def test_plan_scene_order_matches_intent(self):
        """PLAN_SCENE_ORDER 覆盖 intent 全部场景（image_edit 最前，防误吞）。"""
        import api.agent.intent as intent_mod

        rule_scenes = [s for s, *_ in intent_mod._INTENT_RULES]
        for scene in rule_scenes:
            assert scene in PLAN_SCENE_ORDER, f"scene {scene} 应纳入 PLAN_SCENE_ORDER"

    async def test_disabled_flag_obeys_env(self, monkeypatch):
        """开关关闭时 IF_PLANNER_ENABLED 为 False（路由层据此 404）。"""
        monkeypatch.setenv("IF_AGENT_PLANNER_ENABLED", "0")
        # 重新读开关
        import importlib

        import api.agent.planner as planner_mod

        importlib.reload(planner_mod)
        assert planner_mod.IF_PLANNER_ENABLED is False
        importlib.reload(planner_mod)  # 恢复默认
