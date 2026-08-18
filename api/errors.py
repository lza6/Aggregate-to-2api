"""统一错误响应格式和错误码。

用法：
    raise AppError("QUEUE_FULL", "队列已满，请稍后重试", status_code=429)
    return error_response("QUEUE_FULL", "队列已满", status_code=429)
"""

from fastapi.responses import JSONResponse
from typing import Any


class AppError(Exception):
    """统一的应用错误。"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict | None = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


def error_response(
    code: str,
    message: str,
    status_code: int = 400,
    details: dict | None = None,
) -> JSONResponse:
    """统一错误响应格式。"""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


# ── 错误码常量 ──────────────────────────────────────
# 使用方式：raise AppError(ErrorCodes.QUEUE_FULL, "队列已满")


class ErrorCodes:
    """错误码常量定义，附 HTTP 状态码建议。"""

    QUEUE_FULL = "QUEUE_FULL"                         # 429 队列满
    RATE_LIMITED = "RATE_LIMITED"                     # 429 限流
    INVALID_MODEL = "INVALID_MODEL"                   # 422 模型不存在
    INVALID_PROMPT = "INVALID_PROMPT"                 # 422 提示词不符合要求
    INVALID_RATIO = "INVALID_RATIO"                   # 422 比例格式错误
    PROVIDER_DOWN = "PROVIDER_DOWN"                   # 503 提供商不可用
    SOLVER_CIRCUIT_OPEN = "SOLVER_CIRCUIT_OPEN"       # 503 求解器熔断
    TASK_TIMEOUT = "TASK_TIMEOUT"                     # 408 生成超时
    PROVIDER_OUT_OF_CREDITS = "PROVIDER_OUT_OF_CREDITS"  # 429 提供商额度耗尽
    NOT_FOUND = "NOT_FOUND"                           # 404 资源不存在
    UNAUTHORIZED = "UNAUTHORIZED"                     # 401 未授权
    IDEMPOTENCY_KEY_EXISTS = "IDEMPOTENCY_KEY_EXISTS"  # 409 幂等 Key 冲突
    BAD_REQUEST = "BAD_REQUEST"                       # 400 通用错误
    INTERNAL_ERROR = "INTERNAL_ERROR"                 # 500 服务器内部错误