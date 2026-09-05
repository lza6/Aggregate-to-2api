"""P1-A4：provider 风险档案 Tier + PreToolUse 硬门禁。

参考 OWASP-MCP-Governance Tier + agent-guardrails PreToolUse jq 硬 block：
- provider Tier：free（公益低）/ metered（免费但有限额）/ paid（付费高，预算=0 红线）
- PreToolUse 硬门禁：
  - paid Tier provider 的真实调用需用户明确批准（默认拦截）
  - 破坏性命令（DROP imagefree.db / 批量删邮箱）硬 block
  - allowlist 配套防误伤

开关：IF_PROVIDER_RISK_TIER=0 关闭，回退原无门禁行为（零回归）。
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("agent.guard")

# P1-A4 开关：默认开启，回滚置 0 即回退原无门禁行为
PROVIDER_RISK_TIER_ENABLED = os.getenv("IF_PROVIDER_RISK_TIER", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# 允许真实付费调用的 provider 白名单（用户明确批准后加入）
# 默认空：fal.ai 等付费 provider 真实调用默认拦截
_PAID_ALLOWLIST: set[str] = set()


def add_to_paid_allowlist(provider_prefix: str) -> None:
    """把 provider 加入付费调用白名单（用户明确批准后调用）。"""
    _PAID_ALLOWLIST.add(provider_prefix)
    log.info("provider %s 已加入付费调用白名单", provider_prefix)


def remove_from_paid_allowlist(provider_prefix: str) -> None:
    """从付费白名单移除（收回授权）。"""
    _PAID_ALLOWLIST.discard(provider_prefix)


def is_paid_allowed(provider_prefix: str) -> bool:
    """provider 是否在付费白名单（用户已批准真实付费调用）。"""
    return provider_prefix in _PAID_ALLOWLIST


# provider Tier 枚举（与 base.Provider.risk_tier 对齐）
class ProviderRiskTier:
    """provider 风险档案 Tier。"""

    FREE = "free"  # 公益低（imagefree/aifreeforever 免费）
    METERED = "metered"  # 免费但有限额（tryingopen）
    PAID = "paid"  # 付费高（fal.ai，预算=0 红线）


def get_provider_tier(provider) -> str:
    """从 provider 实例取风险 Tier（未设置默认 free）。"""
    if provider is None:
        return ProviderRiskTier.FREE
    return getattr(provider, "risk_tier", ProviderRiskTier.FREE) or ProviderRiskTier.FREE


def guard_paid_call(provider, action: str = "generate") -> bool:
    """PreToolUse 硬门禁：检查 paid Tier provider 是否允许真实调用。

    返回 True=允许，False=拦截。
    - free/metered Tier：始终允许（无付费红线）
    - paid Tier：需在白名单（用户明确批准）才允许，否则拦截
    - 开关关闭：始终允许（回退原无门禁行为）
    """
    if not PROVIDER_RISK_TIER_ENABLED:
        return True
    tier = get_provider_tier(provider)
    if tier != ProviderRiskTier.PAID:
        return True
    prefix = getattr(provider, "prefix", "")
    if is_paid_allowed(prefix):
        return True
    log.warning("PreToolUse 硬门禁拦截 paid provider %s 的 %s 调用（未在白名单）", prefix, action)
    return False


# 破坏性命令模式（PreToolUse 硬 block，参考 agent-guardrails jq 解析）
# 覆盖：DROP imagefree.db / DELETE FROM accounts / 批量删邮箱 / VACUUM INTO 覆盖
_DESTRUCTIVE_PATTERNS = [
    r"DROP\s+TABLE",
    r"DROP\s+DATABASE",
    r"DELETE\s+FROM\s+accounts",
    r"DELETE\s+FROM\s+email_registry",
    r"DELETE\s+FROM\s+account_pool",
    r"TRUNCATE\s+TABLE",
    r"VACUUM\s+INTO.*\.\.",  # 路径遍历防 VACUUM INTO 覆盖敏感文件
    r"rm\s+-rf\s+/",
    r"git\s+reset\s+--hard",
    r"git\s+clean\s+-fd",
    r"git\s+push\s+--force",
]

# allowlist：某些场景下需放行的破坏性命令（运维明确授权后加）
_DESTRUCTIVE_ALLOWLIST: set[str] = set()


def is_destructive_command(command: str) -> bool:
    """检查命令是否破坏性（PreToolUse 硬 block 用）。

    匹配 _DESTRUCTIVE_PATTERNS 且不在 allowlist → True（拦截）。
    """
    if not command:
        return False
    import re

    for pattern in _DESTRUCTIVE_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            if command.strip() in _DESTRUCTIVE_ALLOWLIST:
                return False
            return True
    return False


def allow_destructive_command(command: str) -> None:
    """把命令加入破坏性 allowlist（运维明确授权后加）。"""
    _DESTRUCTIVE_ALLOWLIST.add(command.strip())


__all__ = [
    "PROVIDER_RISK_TIER_ENABLED",
    "ProviderRiskTier",
    "add_to_paid_allowlist",
    "allow_destructive_command",
    "get_provider_tier",
    "guard_paid_call",
    "is_destructive_command",
    "is_paid_allowed",
    "remove_from_paid_allowlist",
]
