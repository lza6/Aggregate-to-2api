"""全局异常处理器（v4.2 拆分：main.py 迁移）。"""
from __future__ import annotations

import logging

from starlette.exceptions import HTTPException as StarletteHTTPException

from .errors import AppError, ErrorCodes, error_response, STATUS_CODE_ERROR_MAP
from .error_tracker import record as error_tracker_record

log = logging.getLogger("imagefree_api")


async def app_error_handler(request, exc: AppError):
    """AppError → 统一错误响应格式。"""
    error_tracker_record(exc.code)
    return error_response(exc.code, exc.message, exc.status_code, exc.details)


async def starlette_http_exception_handler(request, exc: StarletteHTTPException):
    """HTTPException → 统一错误响应格式（状态码/SQL/业务），映射到标准错误码。"""
    _status_code = exc.status_code
    _message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    error_tracker_record(STATUS_CODE_ERROR_MAP.get(_status_code, ErrorCodes.BAD_REQUEST))
    return error_response(
        STATUS_CODE_ERROR_MAP.get(_status_code, ErrorCodes.BAD_REQUEST),
        _message,
        _status_code,
    )


async def generic_exception_handler(request, exc: Exception):
    """未捕获的异常 → 500（避免栈溢出到客户端）。"""
    log.exception("未捕获的异常: %s", exc)
    error_tracker_record(ErrorCodes.INTERNAL_ERROR)
    return error_response(
        ErrorCodes.INTERNAL_ERROR,
        "服务器内部错误",
        status_code=500,
    )


def register_exception_handlers(app) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)