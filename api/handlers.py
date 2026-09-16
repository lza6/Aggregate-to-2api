"""全局异常处理器（v4.2 拆分：main.py 迁移）。"""

from __future__ import annotations

import logging

from starlette.exceptions import HTTPException as StarletteHTTPException

from .error_tracker import record as error_tracker_record
from .errors import STATUS_CODE_ERROR_MAP, AppError, ErrorCodes, error_response

log = logging.getLogger("imagefree_api")


def _retry_after_seconds(details: dict) -> int:
    """从 AppError.details 取 retry_after_seconds；缺失/非法回退 60 秒（P1-5）。"""
    raw = details.get("retry_after_seconds")
    if raw is None:
        return 60
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return 60
    return max(1, val)


async def app_error_handler(request, exc: AppError):
    """AppError → 统一错误响应格式。

    P1-5：429 时补面向用户的字段——`retry_after_seconds`（int）与 `human_hint`
    （中文，去技术化），并设置 Retry-After 响应头（优先 guard 算出的真实值，
    缺失时按 60 秒兜底，如聊天上游 ProviderRateLimited 升级的 429）。
    """
    error_tracker_record(exc.code)
    headers: dict[str, str] | None = None
    details = exc.details or {}
    error_extra: dict | None = None
    if exc.status_code == 429:
        retry_after = _retry_after_seconds(details)
        # 字段同时放在 error 顶层（便于客户端直接消费）与 details（保留扩展区）
        error_extra = {
            "retry_after_seconds": retry_after,
            "human_hint": f"请求太频繁啦，{retry_after} 秒后再试",
        }
        details = {**details, **error_extra}
        headers = {"Retry-After": str(retry_after)}
    return error_response(exc.code, exc.message, exc.status_code, details, headers=headers, error_extra=error_extra)


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
