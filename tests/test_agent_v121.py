"""tests/test_agent_v121.py — v12.0.1 三项深化测试（TDD）。

T1 自反思 critic：fail（retry_count>=2 + 慢 + 短 prompt → score<0.6）→ 单轮 reflection 修正；
   开关关/二轮不递归；pass 路径输出不变。
T2 LLM 工具循环：响应含 [tool:x] → 自动执行 _exec_tool 回填再调一轮（上限迭代）；
   0 迭代关闭；上限防死循环。付费红线：registry 全程 monkeypatch，零真实调用。
T3 human_input 真通道：inbox create→approve/reject/timeout 三态；开关关保持占位；
   审批端点 404/幂等。
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _cfg_reset(monkeypatch):
    """每用例重置 Settings + inbox（进程内状态隔离）。"""
    from api.agent.human_inbox import human_inbox
    from api.config import reset_settings

    reset_settings()
    human_inbox.reset()
    yield
    human_inbox.reset()
    reset_settings()


@pytest.fixture()
def client():
    """human-inbox 端点专用 TestClient（app 已由 conftest lifespan 装配）。"""
    from api.main import app

    with TestClient(app) as c:
        yield c


# ── T1：critic 自反思 ───────────────────────────────────────
class TestCriticReflection:
    async def test_fail_triggers_reflection(self, monkeypatch):
        """mock critic fail（retry>=2+slow+短prompt）→ 输出含 reflection + regen。"""
        from api.routes.agent_dag_exec import _exec_critic

        # fail 条件：score = 1 - 0.2(retry) - 0.1(slow) - 0.15(short) = 0.55 < 0.6
        out = await _exec_critic("短", _reflected=False)
        # review_generation 的 retry_count/duration 默认 0——需注入。用 monkeypatch 直接控 mock 评分：
        # 简化：直接打 review_generation 返回 fail
        assert "critic=" in out  # 基线输出形状（详细 fail 路径见 test_fail_triggers_reflection_injected）

    async def test_fail_triggers_reflection_injected(self, monkeypatch):
        """注入 fail 结果 → 反思路径：输出含 critic=reflection + regen（Mock stable）。"""
        import api.agent.critic as critic_mod
        from api.agent.critic import CriticResult
        from api.routes import agent_dag_exec as exec_mod

        async def _fail_review(*a, **kw):
            return CriticResult(
                pass_check=False,
                score=0.4,
                issues=["watermark_detected", "blurry"],
                recommendation="regenerate",
                reasoning="mock",
            )

        monkeypatch.setattr(critic_mod, "review_generation", _fail_review)
        out = await exec_mod._exec_critic("画一只猫")
        assert "critic=reflection" in out
        assert "watermark_detected" in out
        assert "regen:" in out
        assert "llm-mock" in out  # Mock 路径重生成为 stable 占位

    async def test_fail_reflection_disabled(self, monkeypatch):
        """IF_CRITIC_REFLECTION_ENABLED=0 → fail 保持原输出（无 regen）。"""
        import api.agent.critic as critic_mod
        from api.agent.critic import CriticResult
        from api.config import reset_settings
        from api.routes import agent_dag_exec as exec_mod

        async def _fail_review(*a, **kw):
            return CriticResult(pass_check=False, score=0.4, issues=["x"], recommendation="regenerate", reasoning="")

        monkeypatch.setattr(critic_mod, "review_generation", _fail_review)
        monkeypatch.setenv("IF_CRITIC_REFLECTION_ENABLED", "0")
        reset_settings()
        out = await exec_mod._exec_critic("画一只猫")
        assert "critic=pass:False" in out
        assert "regen:" not in out

    async def test_reflection_not_recursive(self, monkeypatch):
        """_reflected=True（二轮）→ 不再重生成。"""
        import api.agent.critic as critic_mod
        from api.agent.critic import CriticResult
        from api.routes import agent_dag_exec as exec_mod

        async def _fail_review(*a, **kw):
            return CriticResult(pass_check=False, score=0.4, issues=["x"], recommendation="regenerate", reasoning="")

        monkeypatch.setattr(critic_mod, "review_generation", _fail_review)
        out = await exec_mod._exec_critic("画一只猫", _reflected=True)
        assert "regen:" not in out

    async def test_pass_path_unchanged(self):
        """pass 路径输出与 v11 契约一致（零回归）。"""
        from api.routes.agent_dag_exec import _exec_critic

        out = await _exec_critic("画一只高清赛博朋克风格的猫")
        assert out.startswith("critic=pass:True")


# ── T2：LLM 工具调用循环 ────────────────────────────────────
def _patch_registry_provider(monkeypatch, responses: list[str]):
    """注入假 provider：按调用序返回 responses（记录每次 messages）。

    bootstrap 也须置空：真 bootstrap 会访问 registry.providers 填充单例，
    对 Mock _Registry 直接 AttributeError（参考 test_agent_intent_llm._patch_registry）。
    """
    reg_mod = importlib.import_module("api.providers.registry")

    class _Provider:
        def __init__(self):
            self.calls: list[list[dict]] = []

        async def chat_collect(self, model_id, messages, **kw):
            self.calls.append(messages)
            return {"text": responses[min(len(self.calls) - 1, len(responses) - 1)]}

    class _Registry:
        def __init__(self, p):
            self._p = p

        def all_chat_models(self):
            return [type("M", (), {"id": "tryingopen/t1"})()]

        chat_providers = property(lambda self: {"tryingopen": self._p})

    p = _Provider()
    monkeypatch.setattr(reg_mod, "registry", _Registry(p))
    monkeypatch.setattr(reg_mod, "bootstrap", lambda: None)
    return p


class TestLLMToolLoop:
    async def test_tool_loop_executes_and_refills(self, monkeypatch):
        """响应含 [tool:x] → 执行工具 → 回填二轮 → 返回最终文本。"""
        from api.config import reset_settings
        from api.routes.agent_dag_exec import _exec_llm

        provider = _patch_registry_provider(
            monkeypatch, ["我先查技能 [tool:ecommerce-visual-copywriting]", "最终答案：已结合技能完成"]
        )
        monkeypatch.delenv("IF_MOCK_UPSTREAM", raising=False)
        monkeypatch.setenv("IF_LLM_TOOL_ITERATIONS", "2")
        reset_settings()
        out = await _exec_llm("生成电商主图")
        assert out == "最终答案：已结合技能完成"
        assert len(provider.calls) == 2
        # 第二轮 prompt 含工具结果回填
        second_user = provider.calls[1][-1]["content"]
        assert "[工具 ecommerce-visual-copywriting 结果]" in second_user
        assert "已加载技能" in second_user  # _exec_tool 命中 skill 描述

    async def test_tool_loop_disabled_zero_iterations(self, monkeypatch):
        """IF_LLM_TOOL_ITERATIONS=0 → 不循环，原样返回含标记文本。"""
        from api.config import reset_settings
        from api.routes.agent_dag_exec import _exec_llm

        provider = _patch_registry_provider(monkeypatch, ["看 [tool:x]"])
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")  # 组合跑时模块级 setdefault 会固化 mock=1
        monkeypatch.setenv("IF_LLM_TOOL_ITERATIONS", "0")
        reset_settings()
        out = await _exec_llm("测试")
        assert "[tool:x]" in out
        assert len(provider.calls) == 1

    async def test_tool_loop_upper_bound(self, monkeypatch):
        """每轮都返回 [tool:x] → 迭代到上限即止（防死循环）。"""
        from api.config import reset_settings
        from api.routes.agent_dag_exec import _exec_llm

        provider = _patch_registry_provider(monkeypatch, ["[tool:x]"] * 10)
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")  # 同上：显式关 mock + reset 缓存
        monkeypatch.setenv("IF_LLM_TOOL_ITERATIONS", "2")
        reset_settings()
        await _exec_llm("测试")
        assert len(provider.calls) == 3  # 初次 + 2 轮上限


# ── T3：human_input 审批真通道 ──────────────────────────────
class TestHumanInboxStore:
    async def test_approve_flow(self):
        from api.agent.human_inbox import human_inbox

        req = human_inbox.create("run-1", "n1", "确认发布？")
        assert req.status == "pending"
        import asyncio

        wait_task = asyncio.create_task(human_inbox.wait(req.req_id, timeout=5.0))
        await asyncio.sleep(0.1)
        human_inbox.decide(req.req_id, "approve", note="ok")
        final = await wait_task
        assert final.status == "approved" and final.note == "ok"

    async def test_reject_flow(self):
        from api.agent.human_inbox import human_inbox

        req = human_inbox.create("run-1", "n1", "确认？")
        human_inbox.decide(req.req_id, "reject")
        final = await human_inbox.wait(req.req_id, timeout=2.0)
        assert final.status == "rejected"

    async def test_timeout_flow(self):
        from api.agent.human_inbox import human_inbox

        req = human_inbox.create("run-1", "n1", "确认？")
        final = await human_inbox.wait(req.req_id, timeout=0.3, interval=0.05)
        assert final.status == "timeout"

    async def test_decide_idempotent(self):
        """重复决策幂等：仅 pending 可决策。"""
        from api.agent.human_inbox import human_inbox

        req = human_inbox.create("run-1", "n1", "确认？")
        human_inbox.decide(req.req_id, "approve")
        again = human_inbox.decide(req.req_id, "reject")  # 不覆盖
        assert again is not None and again.status == "approved"

    async def test_exec_human_input_placeholder_when_disabled(self):
        """开关关（默认）→ 占位串（v11 零行为变化）。"""
        from api.routes.agent_dag_exec import _exec_human_input

        out = await _exec_human_input("确认发布？")
        assert out.startswith("[human] 等待人工确认")

    async def test_exec_human_input_real_channel_approved(self, monkeypatch):
        """开关开 → 创建请求 + 外部 approve → 返回已批准。"""
        import asyncio

        from api.config import reset_settings
        from api.routes.agent_dag_exec import _exec_human_input

        monkeypatch.setenv("IF_HUMAN_INPUT_ENABLED", "1")
        monkeypatch.setenv("IF_HUMAN_INPUT_TIMEOUT", "5")
        reset_settings()
        from api.agent.human_inbox import human_inbox

        exec_task = asyncio.create_task(_exec_human_input("确认发布？", _human_node_id="n1"))
        await asyncio.sleep(0.1)
        reqs = human_inbox.list(status="pending")
        assert len(reqs) == 1
        human_inbox.decide(reqs[0].req_id, "approve", note="go")
        out = await exec_task
        assert "[human] 已批准" in out and "go" in out


class TestHumanInboxRoutes:
    def test_list_and_decision_api(self, client: TestClient):
        """端到端：create→list→approve→list 状态翻转。"""
        from api.agent.human_inbox import human_inbox

        human_inbox.create("run-x", "n1", "确认？")
        r = client.get("/v1/agent/human-inbox")
        assert r.status_code == 200 and r.json()["count"] == 1
        req_id = r.json()["items"][0]["req_id"]
        r2 = client.post(f"/v1/agent/human-inbox/{req_id}/decision", json={"decision": "approve", "note": "ok"})
        assert r2.status_code == 200 and r2.json()["status"] == "approved"

    def test_decision_unknown_404(self, client: TestClient):
        r = client.post("/v1/agent/human-inbox/nope/decision", json={"decision": "approve"})
        assert r.status_code == 404

    def test_decision_invalid_rejected_422(self, client: TestClient):
        r = client.post("/v1/agent/human-inbox/xxx/decision", json={"decision": "maybe"})
        assert r.status_code == 422
