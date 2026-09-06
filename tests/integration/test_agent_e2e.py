"""tests/integration/test_agent_e2e.py — P1-A1 agent 链路端到端集成测试。

验收：intent → memory → consolidation 完整链路，用 Mock LLM 客户端验证
（付费 API 红线：不真实调 tryingopen 上游；mock_cfsolver 不强依赖，无则 skip）。

覆盖：
- POST /v1/agent/intent → 验证返回结构（scene/confidence/llm_used）
- POST /v1/agent/memory/observe → 验证落库（id>0, stored=True）
- GET  /v1/agent/memory → 验证查询能取到刚写入的 L0 记录
- 直接调 memory_store.consolidate() → Mock LLM 返回压缩结果，L0→L1 提升成功
- 鉴权：复用 conftest 的开放模式（IF_ADMIN_KEY_OPEN=1，无 Key 也放行）
- 指标：埋点后 /metrics 端点能取到 agent_* 计数器
"""

from __future__ import annotations

import asyncio
import importlib
from typing import Any

import pytest
import pytest_asyncio

# 触发 agent.metrics 模块导入，注册 prometheus 指标
import api.agent.metrics  # noqa: F401


def _patch_registry(
    monkeypatch: pytest.MonkeyPatch,
    chat_models: list[Any],
    chat_providers: dict[str, Any],
) -> None:
    """打补丁到 registry 单例 + bootstrap 模块函数。

    参考 tests/test_agent_memory.py:160 的 importlib 模式：
    `import api.providers.registry as reg_mod` 在本项目会被 providers/__init__.py
    的 `from .registry import registry` 拦截，reg_mod 绑成 Registry 实例而非模块。
    """
    reg_mod = importlib.import_module("api.providers.registry")
    reg_singleton = reg_mod.registry

    monkeypatch.setattr(reg_singleton, "all_chat_models", lambda: chat_models)
    for k in list(reg_singleton.chat_providers.keys()):
        monkeypatch.delitem(reg_singleton.chat_providers, k)
    for k, v in chat_providers.items():
        monkeypatch.setitem(reg_singleton.chat_providers, k, v)
    monkeypatch.setattr(reg_mod, "bootstrap", lambda: None)


class _FakeChatProvider:
    """Mock ChatProvider：记录调用参数 + 返回固定 JSON。

    付费 API 红线：不真实调 tryingopen 上游，仅记录参数 + 返回 Mock 响应。
    """

    prefix = "tryingopen"

    def __init__(self, response: dict[str, Any] | None = None,
                 exc: Exception | None = None) -> None:
        self.response = response or {}
        self.exc = exc
        self.calls: list[dict[str, Any]] = []

    async def chat_collect(self, model_id: str, messages: list[dict[str, str]], **kw: Any) -> dict[str, Any]:
        self.calls.append({"model_id": model_id, "messages": messages, "kw": kw})
        if self.exc is not None:
            raise self.exc
        return self.response


def _fake_spec(model_id: str = "tryingopen/fake", provider: str = "tryingopen") -> Any:
    """假的 ModelSpec（鸭子类型）。"""
    return type("Spec", (), {"id": model_id, "provider": provider})()


@pytest_asyncio.fixture
async def app_with_mocks(_app_instance):
    """复用 conftest 的 session 级 app + mock cfsolver，提供 AsyncClient。

    若 mock_cfsolver 启动失败（端口 8001 被占），session fixture 会抛 RuntimeError，
    本 fixture 也跟着 fail——这是 conftest 既有的集成测试门禁。
    """
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=_app_instance.app), base_url="http://test") as client:
        for _ in range(30):
            try:
                r = await client.get("/v1/healthz")
                if r.json().get("status") in ("ok", "degraded"):
                    break
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(0.2)
        yield client


@pytest.mark.integration
class TestAgentE2E:
    """端到端：intent → memory → consolidation 链路（Mock LLM）。"""

    async def test_intent_endpoint_returns_structured_response(self, app_with_mocks, monkeypatch):
        """POST /v1/agent/intent 返回 scene/confidence/llm_used 结构。

        用 Mock LLM 客户端（registry 被 patch），不真实调 tryingopen 上游。
        """
        fake_provider = _FakeChatProvider(
            response={"text": '{"scene":"image","provider_hint":"imagefree","skill_hint":"image-quality-check","confidence":0.85}'}
        )
        _patch_registry(monkeypatch, [_fake_spec()], {"tryingopen": fake_provider})
        # 集成 fixture 默认 IF_MOCK_UPSTREAM=1；这里临时切 0 走真实 LLM 路径（registry 被 Mock）
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")

        r = await app_with_mocks.post("/v1/agent/intent", json={"prompt": "画一只猫"})
        assert r.status_code == 200, f"intent 端点应 200: {r.status_code} {r.text[:200]}"
        body = r.json()
        assert body["scene"] == "image"
        assert body["provider_hint"] == "imagefree"
        assert body["skill_hint"] == "image-quality-check"
        assert body["confidence"] == 0.85
        assert body["llm_used"] is True
        assert body["matched_rule"] == "llm"
        # 验证 LLM 调用参数拼装
        assert len(fake_provider.calls) == 1
        call = fake_provider.calls[0]
        assert call["model_id"] == "tryingopen/fake"
        assert len(call["messages"]) == 2
        assert call["messages"][0]["role"] == "system"
        assert call["messages"][1]["role"] == "user"
        assert call["messages"][1]["content"] == "画一只猫"

    async def test_observe_then_query_l0_round_trip(self, app_with_mocks):
        """POST /v1/agent/memory/observe → GET /v1/agent/memory 落库往返。

        验证 L0 观察写入 + 查询能取回。
        """
        # 先写一条观察
        r = await app_with_mocks.post(
            "/v1/agent/memory/observe",
            json={
                "user_key": "e2e-user",
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

        # 再查询 L0
        r2 = await app_with_mocks.get(
            "/v1/agent/memory?scene=image&layer=L0&limit=10&user_key=e2e-user"
        )
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["enabled"] is True
        assert body2["count"] >= 1
        # 找到刚写入的记录
        found = [r for r in body2["items"] if r["content"] == "用户偏好赛博朋克风格"]
        assert len(found) == 1
        assert found[0]["importance"] == 0.8
        assert found[0]["scene"] == "image"
        assert found[0]["layer"] == "L0"

    async def test_consolidation_with_mock_llm_promotes_l0_to_l1(self, app_with_mocks, monkeypatch, tmp_path):
        """直接调 memory_store.consolidate() 验证 L0→L1 提升（Mock LLM）。

        用独立 db_path 避免污染 session 级共享 DB。
        """
        from api.agent.memory import MemoryStore

        store = MemoryStore(str(tmp_path / "e2e_consolidation.db"))
        # 写两条 L0 观察
        await store.observe("u1", "image", "事实A", 0.9)
        await store.observe("u1", "image", "事实B", 0.8)

        # Mock LLM 返回压缩行格式（importance|content）
        fake_provider = _FakeChatProvider(
            response={"text": "0.8|压缩原子事实A\n0.6|压缩原子事实B\n0.2|低重要性忽略"}
        )
        _patch_registry(monkeypatch, [_fake_spec()], {"tryingopen": fake_provider})
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")

        result = await store.consolidate()
        assert result["L0_to_L1"] == 2  # importance>=0.5 的两条
        assert result["pruned"] == 0

        # 验证 L0 已清空
        l0 = await store.query("u1", "image", layer="L0", limit=10)
        assert len(l0) == 0
        # L1 有 2 条压缩后的原子事实
        l1 = await store.query("u1", "image", layer="L1", limit=10)
        assert len(l1) == 2
        contents = {r.content for r in l1}
        assert "压缩原子事实A" in contents
        assert "压缩原子事实B" in contents

    async def test_consolidation_metric_incremented_on_success(self, app_with_mocks, monkeypatch, tmp_path):
        """consolidate success 分支触发 agent_memory_consolidations_total{result=success} +1。"""
        from prometheus_client import REGISTRY

        from api.agent.memory import MemoryStore

        collector = REGISTRY._names_to_collectors.get("agent_memory_consolidations_total")
        assert collector is not None, "agent_memory_consolidations_total 必须已注册"
        v_before = REGISTRY.get_sample_value(
            "agent_memory_consolidations_total", {"result": "success"}
        ) or 0.0

        store = MemoryStore(str(tmp_path / "e2e_metric.db"))
        await store.observe("u1", "image", "事实A", 0.9)

        fake_provider = _FakeChatProvider(
            response={"text": "0.8|压缩原子事实A"}
        )
        _patch_registry(monkeypatch, [_fake_spec()], {"tryingopen": fake_provider})
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")

        await store.consolidate()

        v_after = REGISTRY.get_sample_value(
            "agent_memory_consolidations_total", {"result": "success"}
        ) or 0.0
        assert v_after == v_before + 1, f"success 计数应 +1（before={v_before}, after={v_after}）"

    async def test_metrics_endpoint_exposes_agent_counters(self, app_with_mocks, monkeypatch):
        """/metrics 端点暴露 agent_intent_classifications_total / agent_llm_calls_total。

        先触发一次 intent 调用（Mock LLM）让计数器有样本，再 GET /metrics 验证文本含指标名。
        """
        fake_provider = _FakeChatProvider(
            response={"text": '{"scene":"chat","provider_hint":"tryingopen","confidence":0.7}'}
        )
        _patch_registry(monkeypatch, [_fake_spec()], {"tryingopen": fake_provider})
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")

        # 触发一次 intent 分类（让 counter 有样本）
        r = await app_with_mocks.post("/v1/agent/intent", json={"prompt": "随便聊聊"})
        assert r.status_code == 200
        body = r.json()
        assert body["llm_used"] is True

        # GET /metrics 验证指标名出现
        m = await app_with_mocks.get("/metrics")
        assert m.status_code == 200
        text = m.text
        assert "agent_intent_classifications_total" in text, "/metrics 必须暴露 agent_intent_classifications_total"
        assert "agent_llm_calls_total" in text, "/metrics 必须暴露 agent_llm_calls_total"
        assert "agent_memory_consolidations_total" in text, "/metrics 必须暴露 agent_memory_consolidations_total"
        assert "agent_critic_reviews_total" in text, "/metrics 必须暴露 agent_critic_reviews_total"

    async def test_intent_endpoint_rejects_empty_prompt(self, app_with_mocks):
        """POST /v1/agent/intent 空 prompt → 422（IntentRequest min_length=1）。"""
        r = await app_with_mocks.post("/v1/agent/intent", json={"prompt": ""})
        assert r.status_code == 422

    async def test_observe_endpoint_rejects_invalid_importance(self, app_with_mocks):
        """POST /v1/agent/memory/observe importance=1.5 → 422（pydantic ge=0 le=1）。"""
        r = await app_with_mocks.post(
            "/v1/agent/memory/observe",
            json={"scene": "image", "content": "test", "importance": 1.5},
        )
        assert r.status_code == 422

    async def test_health_endpoint_returns_all_switches(self, app_with_mocks):
        """GET /v1/agent/health 返回 4 开关状态 + 4 表名映射。"""
        r = await app_with_mocks.get("/v1/agent/health")
        assert r.status_code == 200
        body = r.json()
        assert "intent_classifier" in body
        assert "memory_consolidation" in body
        assert "provider_risk_tier" in body
        assert isinstance(body["intent_classifier"], bool)
        tables = body["memory_tables"]
        assert tables["L0"] == "mem_observations"
        assert tables["L1"] == "mem_atoms"
        assert tables["L2"] == "mem_scenarios"
        assert tables["L3"] == "mem_persona"
