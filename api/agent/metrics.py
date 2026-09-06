"""Agent 子系统 Prometheus 指标（P1-A1 可观测性）。

复用 prometheus_client 全局 REGISTRY，经 /metrics 端点暴露（见
api/routes/admin/query.py:445 的 imagefree_metrics → generate_latest）。
注册幂等：模块重导入时 _metric 工厂复用同名 collector，不抛 Duplicated timeseries
（参考 api/metrics_ext.py 的同名 _metric 工厂模式）。

指标清单：
- agent_intent_classifications_total{result}   意图分类结果（success/fallback/llm_error）
- agent_critic_reviews_total{result}           终检结果（success/fallback/llm_error）
- agent_memory_consolidations_total{result}    记忆巩固结果（success/fallback/llm_error）
- agent_llm_calls_total{module,intent}         LLM 调用次数（module=intent/critic/memory，
                                                intent=classify/review/consolidate）

埋点位置：
- intent.py _llm_classify：LLM 调用前 inc agent_llm_calls_total；按结果 inc agent_intent_classifications_total
- critic.py _llm_review：同上，module=critic
- memory.py _consolidate_with_llm：同上，module=memory
"""

from __future__ import annotations

from prometheus_client import REGISTRY, Counter


def _metric(factory, name: str, doc: str, labelnames: tuple[str, ...] = ()):
    """注册或复用同名指标（模块重导入幂等，参考 metrics_ext._metric）。

    pytest 会话可能多次 import 本模块（conftest 清 sys.modules 后重建），
    而 prometheus 全局 REGISTRY 不会清——重复注册会抛 Duplicated timeseries。
    本工厂记录上次绝对值，已注册同名指标时复用既有 collector。
    """
    existing = REGISTRY._names_to_collectors.get(name)
    if existing is not None:
        return existing
    return factory(name, doc, labelnames) if labelnames else factory(name, doc)


# 意图分类结果计数（result=success/fallback/llm_error）
agent_intent_classifications_total = _metric(
    Counter,
    "agent_intent_classifications_total",
    "Agent 意图分类结果计数（success=LLM 返回有效 JSON，fallback=无模型/无 provider/格式错误/Mock，llm_error=异常）",
    ("result",),
)

# 终检结果计数
agent_critic_reviews_total = _metric(
    Counter,
    "agent_critic_reviews_total",
    "Agent 终检结果计数（success/fallback/llm_error）",
    ("result",),
)

# 记忆巩固结果计数
agent_memory_consolidations_total = _metric(
    Counter,
    "agent_memory_consolidations_total",
    "Agent 记忆巩固结果计数（success/fallback/llm_error）",
    ("result",),
)

# LLM 调用次数（按模块 + 操作类型）
agent_llm_calls_total = _metric(
    Counter,
    "agent_llm_calls_total",
    "Agent LLM 调用次数（module=intent/critic/memory，intent=classify/review/consolidate）",
    ("module", "intent"),
)


def inc_intent_classification(result: str) -> None:
    """安全 inc 意图分类计数器（label 值非法时静默跳过，不崩主链路）。"""
    try:
        agent_intent_classifications_total.labels(result=result).inc()
    except Exception:  # noqa: BLE001  指标埋点不崩主链路
        pass


def inc_critic_review(result: str) -> None:
    """安全 inc 终检计数器。"""
    try:
        agent_critic_reviews_total.labels(result=result).inc()
    except Exception:  # noqa: BLE001
        pass


def inc_memory_consolidation(result: str) -> None:
    """安全 inc 记忆巩固计数器。"""
    try:
        agent_memory_consolidations_total.labels(result=result).inc()
    except Exception:  # noqa: BLE001
        pass


def inc_llm_call(module: str, intent: str) -> None:
    """安全 inc LLM 调用计数器。"""
    try:
        agent_llm_calls_total.labels(module=module, intent=intent).inc()
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "agent_critic_reviews_total",
    "agent_intent_classifications_total",
    "agent_llm_calls_total",
    "agent_memory_consolidations_total",
    "inc_critic_review",
    "inc_intent_classification",
    "inc_llm_call",
    "inc_memory_consolidation",
]
