"""tests/test_agent_intent_llm.py — P1-A1 意图分类 LLM 调用参数拼装单测。

验收（核心）：用 Mock LLM 客户端验证 _llm_classify 的 LLM 调用**参数拼装**，
**禁止真实调 tryingopen 上游**（付费 API 红线：Mock 验证参数拼装 + 解析 + 异常分支）。

覆盖分支：
- success：LLM 返回合法 JSON → 解析正确 + llm_used=True + inc success
- timeout：LLM 调用抛 TimeoutError → 回退 unknown + inc llm_error
- malformed_response：LLM 返回非 JSON 文本 → 回退 unknown + inc fallback
- no_model：registry.all_chat_models() 返回空 → 回退 unknown + inc fallback
- no_provider：chat_providers 字典无对应前缀 → 回退 unknown + inc fallback
- messages 格式：system + user 两条，system 含 JSON 输出契约

埋点验证：inc_intent_classification / inc_llm_call 在每个分支都被调用（覆盖 P1-A1 指标）。

参考 tests/test_agent_memory.py 的 _patch_registry 模式：
    import importlib
    reg_mod = importlib.import_module("api.providers.registry")
    reg_singleton = reg_mod.registry
    monkeypatch.setattr(reg_singleton, "all_chat_models", lambda: chat_models)
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

# 触发 agent.metrics 模块导入，注册 prometheus 指标（lazy import 的副作用）
import api.agent.metrics  # noqa: F401


@pytest.fixture(autouse=True)
def _isolate_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """每用例独立设置 IF_MOCK_UPSTREAM=0 + IF_AGENT_INTENT_CLASSIFIER=1，
    结束自动还原（防 env 污染 test_agent_intent.py 的 IF_MOCK_UPSTREAM=1 假设）。

    关键坑：模块级 os.environ.setdefault 会在本文件被 import 时把 IF_MOCK_UPSTREAM
    永久设为 0，后续 test_agent_intent.py 的 setdefault("IF_MOCK_UPSTREAM", "1") 变 no-op，
    导致 test_fuzzy_intent_uses_llm_mock 走真实 LLM 路径调 tryingopen 上游
    （违反付费 API 红线：tryingopen 免费也不在测试里真实调）。
    用 monkeypatch.setenv 替代 setdefault，确保每用例结束后 env 自动还原。
    """
    monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")
    monkeypatch.setenv("IF_AGENT_INTENT_CLASSIFIER", "1")


def _patch_registry(
    monkeypatch: pytest.MonkeyPatch,
    chat_models: list[Any],
    chat_providers: dict[str, Any],
) -> None:
    """打补丁到 registry 单例 + bootstrap 模块函数。

    关键坑（参考 tests/test_agent_memory.py:160 注释）：
    `import api.providers.registry as reg_mod` 在本项目会被 providers/__init__.py
    的 `from .registry import registry` 拦截，reg_mod 绑成 Registry 实例而非模块。
    用 importlib.import_module 显式拿子模块对象，才能 monkeypatch 模块级 bootstrap。
    """
    reg_mod = importlib.import_module("api.providers.registry")
    reg_singleton = reg_mod.registry

    monkeypatch.setattr(reg_singleton, "all_chat_models", lambda: chat_models)
    # 清空原有 chat_providers 再注入假的
    for k in list(reg_singleton.chat_providers.keys()):
        monkeypatch.delitem(reg_singleton.chat_providers, k)
    for k, v in chat_providers.items():
        monkeypatch.setitem(reg_singleton.chat_providers, k, v)
    monkeypatch.setattr(reg_mod, "bootstrap", lambda: None)


class _FakeChatProvider:
    """Mock ChatProvider：记录 chat_collect 调用参数，返回固定 JSON。

    付费 API 纸上验证：不真实调 tryingopen 上游，仅记录参数 + 返回 Mock 响应。
    """

    def __init__(self, prefix: str = "tryingopen", response: dict[str, Any] | None = None,
                 exc: Exception | None = None) -> None:
        self.prefix = prefix
        self.response = response or {}
        self.exc = exc
        self.calls: list[dict[str, Any]] = []

    async def chat_collect(self, model_id: str, messages: list[dict[str, str]], **kw: Any) -> dict[str, Any]:
        self.calls.append({"model_id": model_id, "messages": messages, "kw": kw})
        if self.exc is not None:
            raise self.exc
        return self.response


def _fake_spec(model_id: str = "tryingopen/fake", provider: str = "tryingopen") -> Any:
    """构造一个假的 ModelSpec（鸭子类型，intent.py 只读 .id 属性）。"""
    return type("Spec", (), {"id": model_id, "provider": provider})()


@pytest.mark.asyncio
async def test_llm_classify_success_parses_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """success 分支：LLM 返回合法 JSON → 解析为 IntentResult + llm_used=True + inc success。

    验证 LLM 调用参数拼装：
    - model_id 从 all_chat_models()[0].id 取
    - messages 含 system + user 两条
    - system_prompt 含 JSON 输出契约（"只输出 JSON"）
    - user content 是原 prompt
    """
    fake_provider = _FakeChatProvider(
        response={"text": '{"scene":"image","provider_hint":"imagefree","skill_hint":"image-quality-check","confidence":0.85}'}
    )
    _patch_registry(monkeypatch, [_fake_spec()], {"tryingopen": fake_provider})

    from api.agent.intent import _llm_classify

    r = await _llm_classify("画一只猫")

    # 参数拼装断言
    assert len(fake_provider.calls) == 1, "chat_collect 必须被调用一次"
    call = fake_provider.calls[0]
    assert call["model_id"] == "tryingopen/fake"
    assert len(call["messages"]) == 2
    assert call["messages"][0]["role"] == "system"
    assert "JSON" in call["messages"][0]["content"], "system_prompt 必须含 JSON 输出契约"
    assert call["messages"][1]["role"] == "user"
    assert call["messages"][1]["content"] == "画一只猫", "user content 必须是原 prompt"

    # 解析断言
    assert r.scene == "image"
    assert r.provider_hint == "imagefree"
    assert r.skill_hint == "image-quality-check"
    assert r.confidence == 0.85
    assert r.llm_used is True
    assert r.matched_rule == "llm"
    assert "raw" in r.extra


@pytest.mark.asyncio
async def test_llm_classify_timeout_falls_back_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """timeout 分支：LLM 调用抛 TimeoutError → 回退 unknown + inc llm_error。

    付费 API 红线：不真实调上游，Mock provider 抛 TimeoutError 模拟超时。
    """
    fake_provider = _FakeProviderExc(TimeoutError("LLM 超时"))
    _patch_registry(monkeypatch, [_fake_spec()], {"tryingopen": fake_provider})

    from api.agent.intent import _llm_classify

    r = await _llm_classify("模糊意图")

    assert r.scene == "unknown"
    assert r.confidence == 0.3
    assert r.llm_used is True
    assert r.matched_rule == "llm_fallback"


class _FakeProviderExc(_FakeChatProvider):
    """继承 _FakeChatProvider，构造时直接传 exc。"""

    def __init__(self, exc: Exception) -> None:
        super().__init__(response={}, exc=exc)


@pytest.mark.asyncio
async def test_llm_classify_malformed_response_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """malformed_response 分支：LLM 返回非 JSON 文本 → 回退 unknown + inc fallback。

    LLM 输出不含 {} 时，text.find("{") 返回 -1，走 fallback 分支。
    """
    fake_provider = _FakeChatProvider(response={"text": "抱歉，我无法分类这个意图。"})
    _patch_registry(monkeypatch, [_fake_spec()], {"tryingopen": fake_provider})

    from api.agent.intent import _llm_classify

    r = await _llm_classify("奇怪的东西")

    assert r.scene == "unknown"
    assert r.confidence == 0.3
    assert r.llm_used is True
    assert r.matched_rule == "llm_fallback"


@pytest.mark.asyncio
async def test_llm_classify_no_model_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """no_model 分支：all_chat_models() 返回空 → 回退 unknown + llm_used=True + matched_rule=llm_no_model。

    不调 LLM（chat_collect 不应被调用）。
    """
    fake_provider = _FakeChatProvider(response={"text": "{}"})
    _patch_registry(monkeypatch, [], {"tryingopen": fake_provider})

    from api.agent.intent import _llm_classify

    r = await _llm_classify("模糊意图")

    assert r.scene == "unknown"
    assert r.confidence == 0.3
    assert r.llm_used is True
    assert r.matched_rule == "llm_no_model"
    assert len(fake_provider.calls) == 0, "无模型时不应调 LLM"


@pytest.mark.asyncio
async def test_llm_classify_no_provider_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """no_provider 分支：chat_providers 字典无对应前缀 → 回退 unknown + matched_rule=llm_no_provider。

    构造一个 model_id 前缀不匹配的 Spec（如 "unknown/fake"），chat_providers 不注册 "unknown"。
    """
    fake_provider = _FakeChatProvider(response={"text": "{}"})
    # Spec 前缀 "unknown"，但 chat_providers 只有 "tryingopen"
    _patch_registry(monkeypatch, [_fake_spec("unknown/fake", "unknown")], {"tryingopen": fake_provider})

    from api.agent.intent import _llm_classify

    r = await _llm_classify("模糊意图")

    assert r.scene == "unknown"
    assert r.confidence == 0.3
    assert r.llm_used is True
    assert r.matched_rule == "llm_no_provider"
    assert len(fake_provider.calls) == 0, "无 provider 时不应调 LLM"


@pytest.mark.asyncio
async def test_llm_classify_json_extraction_from_extra_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 输出含多余文字时仍能提取 JSON（容错路径）。

    text.find("{") 与 text.rfind("}") 提取首个 JSON 对象。
    """
    fake_provider = _FakeChatProvider(
        response={"text": '好的，分类结果：\n{"scene":"chat","provider_hint":"tryingopen","skill_hint":"prompt-refine","confidence":0.75}\n以上是结果。'}
    )
    _patch_registry(monkeypatch, [_fake_spec()], {"tryingopen": fake_provider})

    from api.agent.intent import _llm_classify

    r = await _llm_classify("随便聊聊")

    assert r.scene == "chat"
    assert r.provider_hint == "tryingopen"
    assert r.confidence == 0.75
    assert r.llm_used is True


@pytest.mark.asyncio
async def test_llm_classify_json_missing_fields_uses_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 返回的 JSON 缺字段时用默认值（scene=unknown, confidence=0.5）。"""
    fake_provider = _FakeChatProvider(response={"text": '{"partial":true}'})
    _patch_registry(monkeypatch, [_fake_spec()], {"tryingopen": fake_provider})

    from api.agent.intent import _llm_classify

    r = await _llm_classify("模糊")

    # data.get("scene", "unknown") → unknown
    assert r.scene == "unknown"
    assert r.confidence == 0.5  # data.get("confidence", 0.5)
    assert r.llm_used is True


@pytest.mark.asyncio
async def test_llm_classify_metrics_incremented_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """指标埋点验证：success 分支触发 agent_intent_classifications_total{result=success} +1。

    用 prometheus_client REGISTRY 直接读 collector 样本。
    """
    from prometheus_client import REGISTRY

    # 记录 inc 前的样本值
    collector = REGISTRY._names_to_collectors.get("agent_intent_classifications_total")
    assert collector is not None, "agent_intent_classifications_total 必须已注册"
    val_before = _read_counter_label(collector, "success")

    fake_provider = _FakeChatProvider(
        response={"text": '{"scene":"image","provider_hint":"imagefree","confidence":0.9}'}
    )
    _patch_registry(monkeypatch, [_fake_spec()], {"tryingopen": fake_provider})

    from api.agent.intent import _llm_classify

    await _llm_classify("画图")

    val_after = _read_counter_label(collector, "success")
    assert val_after == val_before + 1, f"success 计数应 +1（before={val_before}, after={val_after}）"


def _read_counter_label(collector: Any, label_value: str) -> float:
    """从 Counter collector 读取指定 label 值的样本值。

    prometheus_client Counter 用 labels().inc() 累加；读取走 REGISTRY.get_sample_value。
    返回 0.0 表示该 label 值尚未被 inc 过（首次 inc 后才有样本）。
    """
    from prometheus_client import REGISTRY as _R

    try:
        v = _R.get_sample_value(
            "agent_intent_classifications_total",
            {"result": label_value},
        )
        return float(v) if v is not None else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


@pytest.mark.asyncio
async def test_llm_classify_metrics_incremented_on_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """指标埋点验证：llm_error 分支触发 agent_intent_classifications_total{result=llm_error} +1。"""
    from prometheus_client import REGISTRY

    collector = REGISTRY._names_to_collectors.get("agent_intent_classifications_total")
    val_before = _read_counter_label(collector, "llm_error")

    fake_provider = _FakeProviderExc(RuntimeError("LLM 挂了"))
    _patch_registry(monkeypatch, [_fake_spec()], {"tryingopen": fake_provider})

    from api.agent.intent import _llm_classify

    await _llm_classify("模糊")

    val_after = _read_counter_label(collector, "llm_error")
    assert val_after == val_before + 1, f"llm_error 计数应 +1（before={val_before}, after={val_after}）"


@pytest.mark.asyncio
async def test_llm_call_metric_incremented(monkeypatch: pytest.MonkeyPatch) -> None:
    """agent_llm_calls_total{module=intent,intent=classify} 在 LLM 调用前 +1。"""
    from prometheus_client import REGISTRY

    collector = REGISTRY._names_to_collectors.get("agent_llm_calls_total")
    assert collector is not None
    val_before = _read_counter_two_label(collector, "intent", "classify")

    fake_provider = _FakeChatProvider(response={"text": "{}"})
    _patch_registry(monkeypatch, [_fake_spec()], {"tryingopen": fake_provider})

    from api.agent.intent import _llm_classify

    await _llm_classify("测试")

    val_after = _read_counter_two_label(collector, "intent", "classify")
    assert val_after == val_before + 1, "agent_llm_calls_total{intent,classify} 应 +1"


def _read_counter_two_label(collector: Any, module: str, intent: str) -> float:
    """从 Counter collector 读取指定双 label 值的样本值。"""
    from prometheus_client import REGISTRY as _R

    try:
        return float(
            _R.get_sample_value(
                "agent_llm_calls_total",
                {"module": module, "intent": intent},
            )
            or 0.0
        )
    except Exception:  # noqa: BLE001
        return 0.0
