"""api/utils/fencing.py — v12.0.0 P1-M10 Fence 清洗层（防提示注入）。

在把不可信文本（上游 API 返回、用户输入、工具结果）喂给 LLM 前清洗，
对齐 commerce-agents `commerce_common/fencing.py:20-149` 的工业级实现思想：

清洗四类威胁（迭代到不动点 fixpoint）：
1. 不可见 Unicode：零宽字符（U+200B-200D/U+2060/U+FEFF）、bidi 控制（U+202A-202E/U+2066-2069）、
   变体选择符（U+FE00-FE0F）
2. C0/C1 控制符（除 \\t\\n\\r）
3. 伪造角色边界：行首 `system:` / `user:` / `assistant:` / `human:` / `ai:`（LLM 会当成真实轮次）
4. 伪造 transcript/工具标签：`<tool_result>` `<system>` `<|im_start|>` 等

设计：纯函数、无状态、`sanitize_text` 迭代到不动点（防清洗产物重组出新载荷）；
`sanitize_value` 递归清洗 dict/list；`max_chars` 截断并把截断后缀计入预算。

开关：IF_FENCING_ENABLED（config，缺省 False 零行为变化；调用方按需开启）。
"""

from __future__ import annotations

import re

__all__ = ["sanitize_text", "sanitize_value", "fencing_enabled"]

# 迭代上限（防极端构造；正常文本 1-2 轮即收敛）
_MAX_PASSES = 5

# 1) 不可见 Unicode（零宽/bidi/变体选择符）
_INVISIBLE_RE = re.compile(
    "[​-‍⁠﻿‪-‮⁦-⁩︀-️­]"
)

# 2) C0/C1 控制符（保留 \t \n \r）
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

# 3) 伪造角色边界（行首；大小写不敏感）
_ROLE_RE = re.compile(
    r"(?im)^(?:\s{0,3})(?:system|user|assistant|human|ai)\s{0,1}:(?!//)"
)

# 4) 伪造 transcript / 工具 / 特殊标签（含 <|im_start|> 变体：'<' 后允许 / 与 |）
_FAKE_TAG_RE = re.compile(
    r"(?i)<[/|]?(?:tool_result|tool_call|system|im_start|im_end|antml|function_results|"
    r"artifact|thinking)\b[^>\n]{0,80}>"
)


def _is_stable(text: str) -> bool:
    """清洗是否已收敛（无新命中）。"""
    return not (
        _INVISIBLE_RE.search(text)
        or _CONTROL_RE.search(text)
        or _ROLE_RE.search(text)
        or _FAKE_TAG_RE.search(text)
    )


def sanitize_text(text: str, *, max_chars: int = 0) -> str:
    """清洗不可信文本到不动点；max_chars>0 时截断（后缀计入预算）。

    返回清洗后的文本。输入非 str 时原样返回（调用方自行保证类型）。
    """
    if not isinstance(text, str):
        return text  # type: ignore[return-value]  # 纯函数契约：非 str 原样透传
    out = text
    for _ in range(_MAX_PASSES):
        if _is_stable(out):
            break
        out = _INVISIBLE_RE.sub("", out)
        out = _CONTROL_RE.sub("", out)
        out = _ROLE_RE.sub("[filtered-role]", out)
        out = _FAKE_TAG_RE.sub("[filtered-tag]", out)
    if max_chars and len(out) > max_chars:
        out = out[:max_chars]
    return out


def sanitize_value(value: object, *, max_chars: int = 0) -> object:
    """递归清洗 dict/list/str（API 响应/工具结果整体过 Fence）。"""
    if isinstance(value, str):
        return sanitize_text(value, max_chars=max_chars)
    if isinstance(value, dict):
        return {
            str(k): sanitize_value(v, max_chars=max_chars)
            for k, v in value.items()  # type: ignore[union-attr]
        }
    if isinstance(value, list):
        return [sanitize_value(v, max_chars=max_chars) for v in value]  # type: ignore[union-attr]
    return value


def fencing_enabled() -> bool:
    """IF_FENCING_ENABLED（config 工厂，缺省 False 零行为变化）。"""
    try:
        from ..config import get_settings

        return bool(get_settings().if_fencing_enabled)
    except Exception:
        return False
