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


async def validation_exception_handler(request, exc):
    """参数/请求体校验错误（422）：纳入错误码聚合，但响应保持 FastAPI 默认 422 结构。

    v6.6.1（Reviewer S1 修复）：此前 RequestValidationError 非 StarletteHTTPException 子类，
    三个已注册 handler 均不接它 → 422 从不进 error_tracker。此处记录 VAL.004 后委托 FastAPI
    默认处理器，不改变对调用方的 422 响应契约（{detail: [...]}）。
    """
    error_tracker_record(ErrorCodes.BAD_REQUEST)
    from fastapi.exception_handlers import request_validation_exception_handler

    return await request_validation_exception_handler(request, exc)


def register_exception_handlers(app) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
    try:
        from fastapi.exceptions import RequestValidationError

        app.add_exception_handler(RequestValidationError, validation_exception_handler)
    except Exception:
        pass
