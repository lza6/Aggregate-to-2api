"""IMP-05: 重试策略 - 错误分类、指数退避 + jitter。

为 worker 提供统一的 transient/permanent 错误分类和重试退避计算。
F-04: 新增 AdaptiveRetryStrategy，支持按错误类型分类的自适应退避策略。
"""
import random
import time
from email.utils import parsedate_to_datetime


class AdaptiveRetryStrategy:
    """自适应重试策略：按错误类型分类，自适应退避 + jitter。

    ERROR_TYPES 定义了每种错误类型的退避基值、最大重试次数、jitter 系数。
    """

    MAX_DELAY = 300  # 最大退避延迟（秒）

    ERROR_TYPES: dict[str, dict[str, float | int]] = {
        "rate_limited": {"backoff_base": 30, "max_retries": 5, "jitter": 0.5},
        "token_rejected": {"backoff_base": 5, "max_retries": 3, "jitter": 0.2},
        "timeout": {"backoff_base": 10, "max_retries": 3, "jitter": 0.3},
        "server_error": {"backoff_base": 15, "max_retries": 4, "jitter": 0.4},
        "network_error": {"backoff_base": 5, "max_retries": 2, "jitter": 0.5},
    }

    # 各类错误的消息标记
    RATE_LIMITED_MARKERS = ("429", "rate_limit", "rate limit", "too many requests")
    TOKEN_REJECTED_MARKERS = ("token_rejected", "human verification failed")
    TIMEOUT_MARKERS = ("timeout",)
    SERVER_ERROR_MARKERS = ("5xx", "503", "502", "504", "500")
    NETWORK_ERROR_MARKERS = ("connectionerror", "connection refused", "connection reset")
    PERMANENT_MARKERS = ("422", "400", "404")

    @staticmethod
    def classify(error: object) -> str:
        """将错误分类为具体 error_type 或 'permanent'。

        分类规则（按优先级，首个匹配为准）：
        - rate_limited: 429, rate_limit, too many requests
        - token_rejected: token_rejected, human verification failed
        - timeout: timeout
        - server_error: 5xx
        - network_error: ConnectionError, connection refused, connection reset
        - permanent: 422, 400, 404
        - 默认: timeout（保守重试）
        """
        msg = str(error).lower()

        # 1. httpx 响应状态码检查
        try:
            resp = getattr(error, "response", None)
            if resp is not None:
                status_code = getattr(resp, "status_code", None) or getattr(resp, "status", None)
                if status_code is not None:
                    if status_code == 429:
                        return "rate_limited"
                    if 500 <= status_code < 600:
                        return "server_error"
                    if status_code in (422, 404):
                        return "permanent"
                    if status_code == 400:
                        err_body = str(error).lower()
                        if "rate_limit" in err_body or "rate limit" in err_body:
                            return "rate_limited"
                        return "permanent"
        except (AttributeError, TypeError):
            pass

        # 2. 检查是否是 httpx 连接/超时异常
        if isinstance(error, TimeoutError):
            return "timeout"
        if isinstance(error, ConnectionError):
            return "network_error"

        # 3. 消息标记匹配
        for marker in AdaptiveRetryStrategy.RATE_LIMITED_MARKERS:
            if marker in msg:
                return "rate_limited"

        for marker in AdaptiveRetryStrategy.TOKEN_REJECTED_MARKERS:
            if marker in msg:
                return "token_rejected"

        for marker in AdaptiveRetryStrategy.SERVER_ERROR_MARKERS:
            if marker in msg:
                return "server_error"

        for marker in AdaptiveRetryStrategy.TIMEOUT_MARKERS:
            if marker in msg:
                return "timeout"

        for marker in AdaptiveRetryStrategy.NETWORK_ERROR_MARKERS:
            if marker in msg:
                return "network_error"

        for marker in AdaptiveRetryStrategy.PERMANENT_MARKERS:
            if marker in msg:
                return "permanent"

        # 5. 默认保守：timeout
        return "timeout"

    @staticmethod
    def should_retry(attempt: int, max_retries: int, error: object) -> bool:
        """判断是否应重试。attempt 从 1 开始计数。

        优先使用 error_type 对应的 max_retries，否则使用传入的 max_retries。
        """
        if attempt < 1:
            return False

        error_type = AdaptiveRetryStrategy.classify(error)

        if error_type == "permanent":
            return False

        # 使用 error_type 对应的 max_retries（如果存在），取两者最小值
        type_config = AdaptiveRetryStrategy.ERROR_TYPES.get(error_type)
        type_max = type_config["max_retries"] if type_config is not None else max_retries
        if not isinstance(type_max, int):
            raise TypeError(f"Expected int for max_retries, got {type(type_max).__name__}")
        effective_max = min(type_max, max_retries)

        return attempt < effective_max

    @staticmethod
    def delay(attempt: int, error_type: str) -> float:
        """指数退避 + jitter 延迟计算，上限 300s。

        attempt 从 1 开始计数（第 1 次重试）。
        公式: random.uniform(base*(1-jitter), base*(1+jitter)) * 2^(attempt-1)
        """
        type_config = AdaptiveRetryStrategy.ERROR_TYPES.get(error_type)
        if type_config is None:
            # 未知类型，使用 timeout 配置
            type_config = AdaptiveRetryStrategy.ERROR_TYPES["timeout"]

        base = float(type_config["backoff_base"])
        jitter = float(type_config["jitter"])

        min_delay = base * (1 - jitter)
        max_delay = base * (1 + jitter)
        delay_val = random.uniform(min_delay, max_delay) * (2 ** (attempt - 1))
        return min(delay_val, AdaptiveRetryStrategy.MAX_DELAY)

    @staticmethod
    def delay_from_retry_after(header_value: str | None) -> float | None:
        """解析 Retry-After 响应头。

        支持秒数（整数）和 HTTP 日期两种格式。
        返回延迟秒数，解析失败返回 None。
        """
        if header_value is None:
            return None

        header_value = header_value.strip()
        if not header_value:
            return None

        # 尝试解析为整数秒数
        try:
            return float(header_value)
        except ValueError:
            pass

        # 尝试解析为 HTTP 日期
        try:
            parsed = parsedate_to_datetime(header_value)
            now = time.time()
            future = parsed.timestamp()
            remaining = future - now
            return max(0.0, remaining)
        except (ValueError, OSError, OverflowError):
            return None

    # ── 兼容旧版 RetryPolicy 接口 ────────────────────

    @staticmethod
    def classify_error(error: object) -> str:
        """兼容旧版 classify_error 接口，返回 transient/permanent。"""
        error_type = AdaptiveRetryStrategy.classify(error)
        return "permanent" if error_type == "permanent" else "transient"

    @staticmethod
    def backoff_delay(attempt: int, base_delay: float) -> float:
        """兼容旧版 backoff_delay 接口。

        formula: random(0, base_delay * 2^(attempt-1))
        """
        max_delay = base_delay * (2 ** (attempt - 1))
        return random.uniform(0, max_delay)


# 兼容旧版 from .retry_policy import RetryPolicy
RetryPolicy = AdaptiveRetryStrategy