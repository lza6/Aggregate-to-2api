"""Agent 包（P1-A2/A3/A4/A7）。

子模块：
- intent: 意图分类→Provider/Skill 路由层（规则正则兜底 + LLM 仅处理模糊意图）
- memory: L0-L3 记忆分层 + 异步巩固管道
- guard: PreToolUse 硬门禁（provider Tier + 破坏性命令拦截）
- routes: /v1/agent/* 路由（skills 列表 + memory 查询 + events 事件流）

开关（全部缺省关闭或最小默认，逐步开启）：
- IF_AGENT_INTENT_CLASSIFIER（意图分类 LLM 模式 vs 规则正则兜底）
- IF_MEMORY_CONSOLIDATION_ENABLED（记忆巩固管道）
- IF_PROVIDER_RISK_TIER（provider Tier 硬门禁）
- IF_CRITIC_AGENT_ENABLED（独立终检 Agent）

设计遵循三铁律：不重构公共接口、不造轮子、先测后改。
所有新功能 IF_*_ENABLED 缺省关闭，回滚置 0 即回退原行为。
"""

from __future__ import annotations

from .critic import CRITIC_AGENT_ENABLED, CriticResult, review_generation
from .guard import ProviderRiskTier, guard_paid_call, is_destructive_command
from .intent import IntentResult, classify_intent
from .memory import MemoryStore, memory_store

__all__ = [
    "CRITIC_AGENT_ENABLED",
    "CriticResult",
    "IntentResult",
    "MemoryStore",
    "ProviderRiskTier",
    "classify_intent",
    "guard_paid_call",
    "is_destructive_command",
    "memory_store",
    "review_generation",
]
