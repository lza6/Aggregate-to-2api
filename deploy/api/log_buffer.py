"""内存环形缓冲区日志处理器，供 /v1/logs 端点查询最近日志。"""
from __future__ import annotations

import logging
import time
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
                "logger": record.name,
                "message": record.getMessage(),
            }
            self.buffer.append(entry)
        except Exception:
            self.handleError(record)

    def snapshot(self, lines: int = 50) -> list[dict]:
        entries = list(self.buffer)
        return entries[-lines:]


# 模块级单例，供 main.py 注入日志系统
log_buffer = LogBufferHandler()