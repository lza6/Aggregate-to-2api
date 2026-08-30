"""内存环形缓冲区日志处理器，供 /v1/logs 端点查询最近日志。

B4: 每条日志同时保留结构化字段（level/logger/message/trace_id/req_id/severity/attrs），
文本查看器仍消费 message 字段（向后兼容，旧查看器不坏）；新端点可读结构化字段。
"""

from __future__ import annotations

import logging
from collections import deque


class LogBufferHandler(logging.Handler):
    """内存环形缓冲区日志处理器。maxlen=1000，保留最近 1000 条日志。"""

    def __init__(self, maxlen: int = 1000) -> None:
        super().__init__()
        self.buffer: deque[dict] = deque(maxlen=maxlen)
        self._formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "timestamp": self._formatter.formatTime(record, self._formatter.datefmt),
                "level": record.levelname,
                "severity": record.levelname.lower(),
                "logger": record.name,
                "message": record.getMessage(),
            }
            # B2/B4: 注入 trace_id/req_id（从 contextvars，无活跃请求则省略）
            try:
                from .context import get_current_context

                ctx = get_current_context()
                if ctx is not None:
                    entry["trace_id"] = ctx.effective_trace_id()
                    entry["req_id"] = ctx.request_id
            except Exception:
                pass
            # B4: 结构化 attrs（透传 LogRecord 的非标准属性，供 json-line 消费）
            attrs = {}
            for k, v in record.__dict__.items():
                if k.startswith("attr_") and not k.startswith("_"):
                    attrs[k[6:]] = v
            if attrs:
                entry["attrs"] = attrs
            self.buffer.append(entry)
        except Exception:
            self.handleError(record)

    def snapshot(self, lines: int = 50) -> list[dict]:
        entries = list(self.buffer)
        return entries[-lines:]

    def filter_by_trace_id(self, trace_id: str, lines: int = 200) -> list[dict]:
        """B2: 按全链路 traceId 过滤日志条目（供 /v1/tasks/{id}/logs 精确串联）。"""
        entries = list(self.buffer)
        matched = [e for e in entries if e.get("trace_id") == trace_id]
        return matched[-lines:]


# 模块级单例，供 main.py 注入日志系统
log_buffer = LogBufferHandler()
