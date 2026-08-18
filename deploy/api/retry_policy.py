"""IMP-05: 重试策略 - 错误分类、指数退避 + jitter。

为 worker 提供统一的 transient/permanent 错误分类和重试退避计算。
"""
import random
import time


class RetryPolicy:
    """重试策略：判断是否应重试，计算退避延迟，分类错误。"""

    TRANSIENT_MARKERS = (
        "timeout",
        "429",
        "5xx",
        "connectionerror",
        "token_rejected",
        "human verification failed",
        "connection refused",
        "connection reset",
        "timeout",
        "429 too many requests",
        "503",
        "502",
        "504",
    )

    PERMANENT_MARKERS = (
        "422",
        "400",
        "404",
    )

    @staticmethod
    def classify_error(error: object) -> str:
        """将错误分类为 'transient'（可重试）或 'permanent'（不可重试）。

        分类规则（按优先级，首个匹配为准）：
        - 已知瞬态: timeout, 429, 5xx, ConnectionError, token_rejected
        - 已知永久: 422, 400（非 rate_limit）, 404
        - 默认: 视为 transient（保守重试）
        """
        msg = str(error).lower()

        # 1. 显式 transient 标记
        for marker in RetryPolicy.TRANSIENT_MARKERS:
            if marker in msg:
                return "transient"

        # 2. 检查是否是 httpx 连接/超时异常
        if isinstance(error, (TimeoutError, ConnectionError)):
            return "transient"

        # 3. 检查 httpx 响应状态码
        try:
            status = getattr(error, "response", None)
            if status is not None:
                status_code = getattr(status, "status_code", None) or getattr(status, "status", None)
                if status_code is not None:
                    if status_code in (429,) or (500 <= status_code < 600):
                        return "transient"
                    if status_code in (422, 404):
                        return "permanent"
                    if status_code == 400:
                        err_body = str(error).lower()
                        if "rate_limit" in err_body or "rate limit" in err_body:
                            return "transient"
                        return "permanent"
        except (AttributeError, TypeError):
            pass

        # 4. 400 + rate_limit → transient（先于永久 400 检查）
        if "400" in msg and ("rate_limit" in msg or "rate limit" in msg):
            return "transient"

        # 5. 显式 permanent 标记
        for marker in RetryPolicy.PERMANENT_MARKERS:
            if marker in msg:
                return "permanent"

        # 5. 默认保守：transient
        return "transient"

    @staticmethod
    def should_retry(attempt: int, max_retries: int, error: object) -> bool:
        """判断是否应重试。attempt 从 1 开始计数，max_retries 为最大尝试次数。

        仅当 attempt < max_retries 且错误为 transient 时返回 True。
        """
        if attempt >= max_retries:
            return False
        return RetryPolicy.classify_error(error) == "transient"

    @staticmethod
    def backoff_delay(attempt: int, base_delay: float) -> float:
        """指数退避 + jitter 延迟计算。

        attempt 从 1 开始计数（第 1 次重试）。
        公式: random(0, base_delay * 2^(attempt-1))
        """
        max_delay = base_delay * (2 ** (attempt - 1))
        return random.uniform(0, max_delay)