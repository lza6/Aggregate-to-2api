"""系统提示词模板系统（P0-3，CL4R1T4S 提炼）。

每模型原生人格的地基：ModelSpec.meta 约定键 → 加载模板 → 与用户 system 合并 →
注入 tryingopen 上游的 [SYSTEM INSTRUCTIONS] 块。

约定 meta 键（全部可选，向后兼容）：
- system_prompt_template: str  模板名（对应 api/prompts/templates/<name>.md），缺省走原 [SYSTEM INSTRUCTIONS] 路径
- thinking_mode: str            "none" | "interleaved" | "auto"（默认 none，上游不支持则降级）
- max_thinking_length: int      思考 token 上限（默认 8000）
- refusal_stance: str           "default_help" | "conservative" | "never_refuse"
                                 国内合规红线：never_refuse 强制降级为 default_help
- citation_style: str           "none" | "anthropic_cite" | "perplexity_bracket" | "codex_f_path"
- skills: list[str]             渐进式披露的 skill 名（P1-1 启用，此处仅占位）

开关：IF_PROMPT_TEMPLATES_ENABLED=0 关闭，回退原 [SYSTEM INSTRUCTIONS] 单段注入。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .loader import build_system_prompt, clear_cache, load_template, render_template, strip_header_comment

log = logging.getLogger("prompts")

# P0-3 开关：默认开启，回滚置 0 即回退原 [SYSTEM INSTRUCTIONS] 单段注入路径
PROMPT_TEMPLATES_ENABLED = os.getenv("IF_PROMPT_TEMPLATES_ENABLED", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# 国内合规红线：never_refuse 强制降级（CL4R1T4S Llama4 stance 不可照搬）；
# 白名单制：仅允许 default_help/conservative，未知值一律归 default_help（安全默认）
_ALLOWED_STANCES = {"default_help", "conservative"}
_DEFAULT_STANCE = "default_help"


def _coerce_stance(value: Any) -> str:
    stance = str(value or _DEFAULT_STANCE).strip().lower() or _DEFAULT_STANCE
    if stance not in _ALLOWED_STANCES:
        log.warning("refusal_stance=%s 非白名单值/触发合规红线，降级为 %s", stance, _DEFAULT_STANCE)
        return _DEFAULT_STANCE
    return stance


def resolve_template_name(meta: dict[str, Any] | None) -> str | None:
    """从 ModelSpec.meta 解析模板名。无模板键返回 None（走原路径）。"""
    if not PROMPT_TEMPLATES_ENABLED or not meta:
        return None
    name = meta.get("system_prompt_template")
    if not name or not isinstance(name, str):
        return None
    return name.strip() or None


def compose_system_text(
    user_system: str,
    meta: dict[str, Any] | None,
) -> str:
    """组合最终 system 文本：宪法基线（base.md）+ 模板 + 用户 system。

    - 无模板键 / 开关关闭：原样返回 user_system（向后兼容原 [SYSTEM INSTRUCTIONS] 路径）
    - 有模板键：base 宪法 + 模板正文 + 用户 system 三段拼接
    - meta 中的 thinking_mode/refusal_stance/citation_style/skills 作为变量注入模板
    """
    template_name = resolve_template_name(meta)
    if template_name is None:
        return user_system

    base = load_template("base")  # 宪法基线（AGENTS.md 5 条编译进顶层）
    template_body = load_template(template_name)  # 模板正文（可能为空串，仅记 warn 不崩）

    variables: dict[str, Any] = {
        "thinking_mode": str((meta or {}).get("thinking_mode") or "none"),
        "max_thinking_length": int((meta or {}).get("max_thinking_length") or 8000),
        "refusal_stance": _coerce_stance((meta or {}).get("refusal_stance")),
        "citation_style": str((meta or {}).get("citation_style") or "none"),
        "skills": list((meta or {}).get("skills") or []) or ["（P1-1 启用后填充）"],
    }

    # 剥离模板头部说明块（`> 变量：{...}` 示例行未插值，不应进入最终 system）
    template_body = strip_header_comment(template_body)
    template_body = render_template(template_body, variables)

    parts: list[str] = [p for p in (base, template_body, user_system) if p and p.strip()]
    return "\n\n---\n\n".join(parts) if parts else (user_system or "")


__all__ = [
    "PROMPT_TEMPLATES_ENABLED",
    "build_system_prompt",
    "clear_cache",
    "compose_system_text",
    "load_template",
    "render_template",
    "resolve_template_name",
    "strip_header_comment",
]
