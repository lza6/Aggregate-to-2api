"""worker/dlq.py — 死信队列辅助逻辑（纯函数，无 Engine 依赖）。

P0-4 从 engine.py _process 的 DLQ 推送逻辑拆出。Engine._process 仍持有流程
编排（重试循环、_finish 落库），DLQ 推送与消息构造委托本模块，保持
engine.py 聚焦于主循环与终态落库。

push_dlq_on_exhaust: 重试耗尽后推入死信队列（依赖 db.push_dlq）。
build_dlq_message: 构造 DLQ 错误文案（纯函数，可单测）。
"""

from __future__ import annotations

import logging
from typing import Any

from .. import config

log = logging.getLogger("engine.dlq")

__all__ = ["build_dlq_message", "push_dlq_on_exhaust"]


def build_dlq_message(last_error: str | None, retry_max: int) -> str:
    """构造 DLQ 错误文案。

    last_error 为空时（理论不该，但防御）回退到「重试 N 次耗尽」。
    """
    dlq_note = f"（DLQ: 重试 {retry_max} 次耗尽）"
    if last_error:
        return f"{last_error}{dlq_note}"
    return f"重试 {retry_max} 次耗尽"


async def push_dlq_on_exhaust(
    db: Any,
    task_id: str,
    last_error: str | None,
    retry_max: int,
) -> None:
    """重试耗尽后推入死信队列（仅当 IF_DLQ_ENABLED）。

    依赖 db.push_dlq(task_id, model, error, attempts) 与 db.get(task_id)。
    model 从 DB row 回查，缺省 "default"。
    """
    if not config.IF_DLQ_ENABLED:
        return
    row = await db.get(task_id)
    model = (row.get("model") or "default") if row else "default"
    await db.push_dlq(task_id, model, last_error, retry_max)
    log.info(
        "DLQ: task %s 推入死信队列（model=%s, error=%s, attempts=%d）",
        task_id,
        model,
        last_error,
        retry_max,
    )
