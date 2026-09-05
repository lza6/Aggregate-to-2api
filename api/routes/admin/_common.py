"""admin 路由包共享依赖（P0-7 拆分）。

集中放置各子模块共用的 import 与模块级对象，避免重复声明。
子模块通过 `from ._common import *` 获取所需符号。

相对路径：本文件位于 `api/routes/admin/_common.py`，`...` 指向 `api/` 包，
故 `from ... import config` = `from api import config`。
"""

from __future__ import annotations

import hashlib
import hmac
import inspect
import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter, Query, Request, WebSocket
from fastapi.responses import FileResponse, PlainTextResponse, Response

from ... import config
from ...audit import audit_log
from ...auth import check_admin_key
from ...errors import AppError, ErrorCodes
from ...log_buffer import log_buffer as log_buffer_handler
from ...log_ws import register_ws, unregister_ws
from ...meta import _SLOW_PAGE, _uptime_human, db, engine, gallery_cache, registry
from ...metrics_ext import imagefree_metrics as metrics_v2
from ...provider_probe import provider_probe
from ...slow_log import slow_log as _slow_log
from ...solver_guard import solver_guard

log = logging.getLogger("imagefree_api")

# 共享 router 单例：query/write 子模块通过 `from ._common import *` 拿到同一个
# router 并用 `@router.get(...)` 注册路由，保证 `from api.routes.admin import router`
# 拿到的是挂了全部路由的单一 APIRouter（`router.routes` 直接是 APIRoute 元素，
# 避免 include_router 产生的 _IncludedRouter 包装层破坏 path 断言）。
router = APIRouter()

__all__ = [
    "APIRouter",
    "AppError",
    "ErrorCodes",
    "FileResponse",
    "Path",
    "PlainTextResponse",
    "Query",
    "Request",
    "Response",
    "WebSocket",
    "_SLOW_PAGE",
    "_slow_log",
    "_uptime_human",
    "audit_log",
    "check_admin_key",
    "config",
    "db",
    "engine",
    "gallery_cache",
    "hmac",
    "hashlib",
    "inspect",
    "log",
    "log_buffer_handler",
    "metrics_v2",
    "os",
    "provider_probe",
    "register_ws",
    "registry",
    "solver_guard",
    "time",
    "unregister_ws",
    "router",
]
