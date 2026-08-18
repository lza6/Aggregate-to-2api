"""统一错误响应格式和分层错误码体系。

分层格式：CATEGORY.NNN（如 AUTH.001、SYS.002）
支持多语言错误消息（zh/en）和动态参数插值。
兼容旧版字符串错误码（如 "QUEUE_FULL" → "SYS.002"）。

用法：
    raise AppError(ErrorCodes.QUEUE_FULL, "队列已满，请稍后重试", status_code=429)
    return error_response(ErrorCodes.QUEUE_FULL, "队列已满", status_code=429)
    msg = get_error_message(ErrorCodes.QUEUE_FULL, lang="zh")
"""

from fastapi.responses import JSONResponse
from typing import Any


class ErrorCategory:
    """错误分类常量。"""

    AUTH = "AUTH"                 # 认证/授权
    VALIDATION = "VAL"            # 参数校验
    PROVIDER = "PROV"             # 提供商/上游
    SYSTEM = "SYS"                # 系统内部
    RATE_LIMIT = "RATE"           # 限流/配额


class ErrorCodes:
    """分层错误码常量（CATEGORY.NNN 格式），附 HTTP 状态码建议。"""

    # ── AUTH: 认证/授权 ──
    UNAUTHORIZED = "AUTH.001"                # 401 未授权
    API_KEY_EXPIRED = "AUTH.002"             # 401 API Key 过期

    # ── VAL: 参数校验 ──
    INVALID_MODEL = "VAL.001"                # 422 模型不存在
    INVALID_PROMPT = "VAL.002"               # 422 提示词不符合要求
    INVALID_RATIO = "VAL.003"                # 422 比例格式错误
    BAD_REQUEST = "VAL.004"                  # 400 通用错误

    # ── PROV: 提供商/上游 ──
    PROVIDER_DOWN = "PROV.001"               # 503 提供商不可用
    PROVIDER_OUT_OF_CREDITS = "PROV.002"     # 429 提供商额度耗尽
    SOLVER_CIRCUIT_OPEN = "PROV.003"         # 503 求解器熔断

    # ── SYS: 系统内部 ──
    INTERNAL_ERROR = "SYS.001"               # 500 服务器内部错误
    QUEUE_FULL = "SYS.002"                   # 429 队列满
    NOT_FOUND = "SYS.003"                    # 404 资源不存在
    TASK_TIMEOUT = "SYS.004"                 # 408 生成超时
    IDEMPOTENCY_KEY_EXISTS = "SYS.005"       # 409 幂等 Key 冲突

    # ── RATE: 限流/配额 ──
    RATE_LIMITED = "RATE.001"                # 429 限流


# ── 旧版错误码 → 分层错误码 映射（兼容） ──
_LEGACY_CODE_MAP: dict[str, str] = {
    "QUEUE_FULL": ErrorCodes.QUEUE_FULL,
    "RATE_LIMITED": ErrorCodes.RATE_LIMITED,
    "INVALID_MODEL": ErrorCodes.INVALID_MODEL,
    "INVALID_PROMPT": ErrorCodes.INVALID_PROMPT,
    "INVALID_RATIO": ErrorCodes.INVALID_RATIO,
    "PROVIDER_DOWN": ErrorCodes.PROVIDER_DOWN,
    "SOLVER_CIRCUIT_OPEN": ErrorCodes.SOLVER_CIRCUIT_OPEN,
    "TASK_TIMEOUT": ErrorCodes.TASK_TIMEOUT,
    "PROVIDER_OUT_OF_CREDITS": ErrorCodes.PROVIDER_OUT_OF_CREDITS,
    "NOT_FOUND": ErrorCodes.NOT_FOUND,
    "UNAUTHORIZED": ErrorCodes.UNAUTHORIZED,
    "IDEMPOTENCY_KEY_EXISTS": ErrorCodes.IDEMPOTENCY_KEY_EXISTS,
    "BAD_REQUEST": ErrorCodes.BAD_REQUEST,
    "INTERNAL_ERROR": ErrorCodes.INTERNAL_ERROR,
}


def _resolve_code(code: str) -> str:
    """将旧版错误码映射为分层格式，若已是分层格式则原样返回。"""
    if "." in code:
        return code  # 已是分层格式，直接返回
    return _LEGACY_CODE_MAP.get(code, code)


# ── 多语言错误消息 ──
ERROR_MESSAGES: dict[str, dict[str, str]] = {
    ErrorCodes.UNAUTHORIZED: {
        "zh": "未授权访问，请提供有效的 API Key",
        "en": "Unauthorized access, please provide a valid API Key",
    },
    ErrorCodes.API_KEY_EXPIRED: {
        "zh": "API Key 已过期，请重新生成",
        "en": "API Key has expired, please regenerate",
    },
    ErrorCodes.INVALID_MODEL: {
        "zh": "未知模型：{model}，可选模型见 GET /v1/models",
        "en": "Unknown model: {model}, available models at GET /v1/models",
    },
    ErrorCodes.INVALID_PROMPT: {
        "zh": "提示词不符合要求：{reason}",
        "en": "Invalid prompt: {reason}",
    },
    ErrorCodes.INVALID_RATIO: {
        "zh": "不支持的图片比例：{ratio}（格式需 N:N，如 1:1、16:9）",
        "en": "Unsupported aspect ratio: {ratio} (format N:N, e.g. 1:1, 16:9)",
    },
    ErrorCodes.BAD_REQUEST: {
        "zh": "请求参数错误：{detail}",
        "en": "Bad request: {detail}",
    },
    ErrorCodes.PROVIDER_DOWN: {
        "zh": "提供商 {provider} 暂时不可用，请稍后重试",
        "en": "Provider {provider} is temporarily unavailable, please try again later",
    },
    ErrorCodes.PROVIDER_OUT_OF_CREDITS: {
        "zh": "提供商 {provider} 额度已耗尽",
        "en": "Provider {provider} has run out of credits",
    },
    ErrorCodes.SOLVER_CIRCUIT_OPEN: {
        "zh": "人机验证服务熔断中，请稍后重试",
        "en": "CAPTCHA solver circuit is open, please try again later",
    },
    ErrorCodes.INTERNAL_ERROR: {
        "zh": "服务器内部错误，请稍后重试",
        "en": "Internal server error, please try again later",
    },
    ErrorCodes.QUEUE_FULL: {
        "zh": "队列已满，请稍后重试",
        "en": "Queue is full, please try again later",
    },
    ErrorCodes.NOT_FOUND: {
        "zh": "资源不存在：{resource}",
        "en": "Resource not found: {resource}",
    },
    ErrorCodes.TASK_TIMEOUT: {
        "zh": "任务生成超时（{timeout}秒），请稍后查询结果",
        "en": "Task generation timed out ({timeout}s), please check results later",
    },
    ErrorCodes.IDEMPOTENCY_KEY_EXISTS: {
        "zh": "幂等 Key 已存在：{key}",
        "en": "Idempotency key already exists: {key}",
    },
    ErrorCodes.RATE_LIMITED: {
        "zh": "请求过于频繁，请 {retry_after} 秒后重试",
        "en": "Rate limited, please retry after {retry_after} seconds",
    },
}


def get_error_message(code: str, lang: str = "zh", **kwargs: Any) -> str:
    """获取多语言错误消息，支持动态参数插值。

    Args:
        code: 分层错误码（如 "SYS.002"）或旧版错误码（如 "QUEUE_FULL"）
        lang: 语言，支持 "zh"（中文）和 "en"（英文）
        **kwargs: 消息模板插值参数

    Returns:
        格式化后的错误消息字符串
    """
    resolved = _resolve_code(code)
    msg_templates = ERROR_MESSAGES.get(resolved, {})
    template = msg_templates.get(lang, msg_templates.get("zh", resolved))
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


# ── HTTP 状态码 → 分层错误码 映射（供 main.py 异常处理器复用）──
STATUS_CODE_ERROR_MAP: dict[int, str] = {
    400: ErrorCodes.BAD_REQUEST,
    401: ErrorCodes.UNAUTHORIZED,
    403: ErrorCodes.UNAUTHORIZED,
    404: ErrorCodes.NOT_FOUND,
    408: ErrorCodes.TASK_TIMEOUT,
    409: ErrorCodes.IDEMPOTENCY_KEY_EXISTS,
    413: ErrorCodes.BAD_REQUEST,
    422: ErrorCodes.BAD_REQUEST,
    429: ErrorCodes.RATE_LIMITED,
    500: ErrorCodes.INTERNAL_ERROR,
    503: ErrorCodes.PROVIDER_DOWN,
}


class AppError(Exception):
    """统一的应用错误，自动映射旧版错误码。"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict | None = None,
    ):
        self.code = _resolve_code(code)
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
    """统一错误响应格式，自动映射旧版错误码。"""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": _resolve_code(code),
                "message": message,
                "details": details or {},
            }
        },
    )