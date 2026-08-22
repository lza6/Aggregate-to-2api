"""磁盘日志落盘（P13）：按天滚动文件日志，保留 N 天。

/v1/logs 仍从内存环形缓冲读取（log_buffer.py），本模块只做持久化补充：
root logger 追加 TimedRotatingFileHandler，跨重启可查。
"""
from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def setup_disk_logging(log_dir: str, retention_days: int = 14) -> TimedRotatingFileHandler:
    """挂载按天滚动的文件日志到 root logger，返回 handler（供 shutdown 移除）。"""
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "imagefree-api.log")
    handler = TimedRotatingFileHandler(
        path, when="midnight", backupCount=max(1, retention_days),
        encoding="utf-8", delay=True, utc=True,
    )
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    logging.getLogger().addHandler(handler)
    return handler


def teardown_disk_logging(handler: TimedRotatingFileHandler) -> None:
    """移除并关闭磁盘日志 handler（优雅关闭时调用）。"""
    logging.getLogger().removeHandler(handler)
    handler.close()
