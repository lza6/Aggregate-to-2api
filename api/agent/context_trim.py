"""上下文 token 精简（指南 v18 P2-2，headroom/rtk-master 对标）。

- trim_chat_messages：intent/chat 前保留 system + 最近 N 轮，超长单条截断（防上下文膨胀）
- summarize_for_intent：intent 分类前把裸 prompt 折叠空白 + 截断（只保留关键语义）
- estimate_tokens：轻量 token 估算（中文 1.5 字/token 近似，供压缩比基准）

纯函数零依赖；IF_CTX_TRIM=0（缺省）不影响调用方——由调用方决定是否启用。
"""
from __future__ import annotations

import re

_DEFAULT_MAX_ROUNDS = 3
_DEFAULT_MAX_CHARS = 800
_WS_FOLD = re.compile(r"[ \t\u3000]+")
_NL_FOLD = re.compile(r"\n{3,}")


def estimate_tokens(text: str) -> int:
    """估算 token 数：CJK 字符按 1.5 字/token，其余按 4 字符/token（近似）。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return max(1, round(cjk / 1.5) + round(other / 4))


def fold_whitespace(text: str) -> str:
    """折叠空白/连续换行，降低无效 token。"""
    return _NL_FOLD.sub("\n\n", _WS_FOLD.sub(" ", text)).strip()


def truncate_chars(text: str, max_chars: int = _DEFAULT_MAX_CHARS) -> str:
    """按字符截断（保留前缀 + 省略标记）。"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def trim_chat_messages(
    messages: list[dict[str, str]],
    max_rounds: int = _DEFAULT_MAX_ROUNDS,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> list[dict[str, str]]:
    """保留 system/首条上下文 + 最近 max_rounds 轮，单条超长截断。输入结构 [{role, content}]。"""
    if not messages:
        return []
    head: list[dict[str, str]] = []
    tail: list[dict[str, str]] = []
    for m in messages:
        role = str(m.get("role", "")).lower()
        if role in ("system", "developer"):
            head.append(m)
        else:
            tail.append(m)
    # 保留最近 max_rounds*2 条（round=user+assistant 一对）
    kept_tail = tail[-max_rounds * 2 :]
    out: list[dict[str, str]] = []
    for m in head + kept_tail:
        content = str(m.get("content", ""))
        folded = fold_whitespace(content)
        out.append({"role": m.get("role", "user"), "content": truncate_chars(folded, max_chars)})
    return out


def summarize_for_intent(prompt: str, max_len: int = 500) -> str:
    """intent 前精简：折叠空白 + 截断（保留关键语义，降低 LLM 输入 token）。"""
    return truncate_chars(fold_whitespace(prompt), max_len)
