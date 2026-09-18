"""上下文 token 精简测试（v18 P2-2）。纯本地确定性。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.agent.context_trim import (  # noqa: E402
    estimate_tokens,
    fold_whitespace,
    summarize_for_intent,
    trim_chat_messages,
    truncate_chars,
)


def test_estimate_tokens_basic():
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello world") >= 1
    assert estimate_tokens("深色背景电商主图") >= 2


def test_fold_whitespace_collapses():
    assert fold_whitespace("a   b\u3000c\n\n\n\nd") == "a b c\n\nd"


def test_truncate_chars_marks():
    assert truncate_chars("abc", 5) == "abc"
    assert truncate_chars("abcdef", 4).startswith("abcd")


def test_trim_keeps_system_and_recent_rounds():
    msgs = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"}, {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "q3"}, {"role": "assistant", "content": "a3"},
        {"role": "user", "content": "q4"}, {"role": "assistant", "content": "a4"},
    ]
    out = trim_chat_messages(msgs, max_rounds=2)
    assert out[0]["role"] == "system"
    roles = [m["role"] for m in out[1:]]
    assert roles == ["user", "assistant", "user", "assistant"]  # 最近 2 轮
    assert out[-1]["content"] == "a4"


def test_trim_truncates_long_content():
    msgs = [{"role": "user", "content": "x" * 1000}]
    out = trim_chat_messages(msgs, max_chars=100)
    assert len(out[0]["content"]) <= 101  # 100 + 省略标记


def test_summarize_for_intent():
    s = summarize_for_intent("  我要   生成   电商主图  \n\n\n  深色背景  ", max_len=200)
    assert "  " not in s
    assert "深色背景" in s
    long = summarize_for_intent("长" * 1000, max_len=100)
    assert len(long) <= 101
