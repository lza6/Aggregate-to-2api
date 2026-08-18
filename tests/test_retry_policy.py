"""IMP-05: 重试策略单元测试。

验证 RetryPolicy 的:
- 错误分类（transient vs permanent）
- 是否应重试判断
- 指数退避 + jitter 范围
"""
import random

import pytest

from api.retry_policy import RetryPolicy


class TestClassifyError:
    """RetryPolicy.classify_error 测试。"""

    @pytest.mark.parametrize("err,expected", [
        # 显式 transient
        ("timeout", "transient"),
        ("429 Too Many Requests", "transient"),
        ("503 Service Unavailable", "transient"),
        ("502 Bad Gateway", "transient"),
        ("504 Gateway Timeout", "transient"),
        ("ConnectionError: connection refused", "transient"),
        ("token_rejected: human verification failed", "transient"),
        ("human verification failed", "transient"),
        ("connection reset by peer", "transient"),
        # 显式 permanent
        ("422 Unprocessable Entity", "permanent"),
        ("400 Bad Request", "permanent"),
        ("404 Not Found", "permanent"),
        ("400 rate_limit exceeded", "transient"),
        ("400 rate limit exceeded", "transient"),
        # 未知默认 transient
        ("unknown error occurred", "transient"),
        ("some random exception", "transient"),
    ])
    def test_classify_error(self, err: str, expected: str) -> None:
        assert RetryPolicy.classify_error(err) == expected

    def test_classify_error_timeout_exception(self) -> None:
        assert RetryPolicy.classify_error(TimeoutError("connection timed out")) == "transient"

    def test_classify_error_connection_error(self) -> None:
        assert RetryPolicy.classify_error(ConnectionError("connection refused")) == "transient"

    def test_classify_error_empty_string(self) -> None:
        assert RetryPolicy.classify_error("") == "transient"


class TestShouldRetry:
    """RetryPolicy.should_retry 测试。"""

    def test_should_retry_transient_under_max(self) -> None:
        """transient + attempt < max_retries → 应重试。"""
        assert RetryPolicy.should_retry(1, 3, "timeout") is True

    def test_should_retry_transient_at_max(self) -> None:
        """transient + attempt >= max_retries → 不应重试。"""
        assert RetryPolicy.should_retry(3, 3, "timeout") is False

    def test_should_retry_permanent(self) -> None:
        """permanent 错误 → 不应重试。"""
        assert RetryPolicy.should_retry(1, 3, "422") is False

    def test_should_retry_one_attempt_no_retry(self) -> None:
        """max_retries=1 时不应重试（仅首次尝试）。"""
        assert RetryPolicy.should_retry(1, 1, "timeout") is False


class TestBackoffDelay:
    """RetryPolicy.backoff_delay 测试。"""

    def test_backoff_delay_attempt_1(self) -> None:
        """第 1 次重试: delay ∈ [0, base_delay)。"""
        random.seed(42)
        d = RetryPolicy.backoff_delay(1, 5.0)
        assert 0 <= d <= 5.0

    def test_backoff_delay_attempt_2(self) -> None:
        """第 2 次重试: delay ∈ [0, base_delay*2)。"""
        random.seed(42)
        d = RetryPolicy.backoff_delay(2, 5.0)
        assert 0 <= d <= 10.0

    def test_backoff_delay_attempt_3(self) -> None:
        """第 3 次重试: delay ∈ [0, base_delay*4)。"""
        random.seed(42)
        d = RetryPolicy.backoff_delay(3, 5.0)
        assert 0 <= d <= 20.0

    def test_backoff_delay_attempt_4(self) -> None:
        """第 4 次重试: delay ∈ [0, base_delay*8)。"""
        random.seed(42)
        d = RetryPolicy.backoff_delay(4, 5.0)
        assert 0 <= d <= 40.0

    def test_backoff_delay_different_base(self) -> None:
        """base_delay=2 时退避范围。"""
        random.seed(42)
        d = RetryPolicy.backoff_delay(1, 2.0)
        assert 0 <= d <= 2.0
        d2 = RetryPolicy.backoff_delay(2, 2.0)
        assert 0 <= d2 <= 4.0

    def test_backoff_delay_jitter(self) -> None:
        """延迟不应是固定值（有 jitter）。"""
        random.seed(42)
        vals = [RetryPolicy.backoff_delay(3, 5.0) for _ in range(10)]
        # 有 jitter 时值会变化
        assert len(set(vals)) > 1, "延迟应因 jitter 而有变化"

    def test_backoff_delay_non_negative(self) -> None:
        """退避延迟应 >= 0。"""
        for attempt in range(1, 6):
            d = RetryPolicy.backoff_delay(attempt, 5.0)
            assert d >= 0, f"attempt {attempt}: delay={d} < 0"


class TestIntegrationTransientThenPermanent:
    """transient → permanent 错误类型转换场景。"""

    def test_transient_then_permanent_no_retry(self) -> None:
        """首次错误 transient（重试），第二次 permanent（不重试）。"""
        attempt = 1
        # 第 1 次: transient → 应重试
        assert RetryPolicy.should_retry(attempt, 3, TimeoutError("timeout")) is True
        # 第 2 次: permanent → 不应重试
        assert RetryPolicy.should_retry(2, 3, "422") is False

    def test_all_transient_retry_up_to_max(self) -> None:
        """全部 transient，最多重试到 max_retries-1。"""
        for attempt in range(1, 3):
            assert RetryPolicy.should_retry(attempt, 3, "timeout") is True
        # 第 3 次（attempt == max_retries）→ 不重试
        assert RetryPolicy.should_retry(3, 3, "timeout") is False