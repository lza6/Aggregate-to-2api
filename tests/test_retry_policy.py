"""IMP-05: 重试策略单元测试。

验证 RetryPolicy 的:
- 错误分类（transient vs permanent）
- 是否应重试判断
- 指数退避 + jitter 范围

验证 AdaptiveRetryStrategy 的:
- 各类错误分类
- delay 范围和上限
- Retry-After 解析
- should_retry 判断
"""

import random
import time

import pytest

from api.retry_policy import AdaptiveRetryStrategy, RetryPolicy


class TestClassifyError:
    """RetryPolicy.classify_error 测试。"""

    @pytest.mark.parametrize(
        "err,expected",
        [
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
        ],
    )
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


class TestAdaptiveRetryStrategy:
    """AdaptiveRetryStrategy 新增功能测试。"""

    def test_error_type_classification(self) -> None:
        """verify classify returns correct error type for each category."""
        assert AdaptiveRetryStrategy.classify("429 Too Many Requests") == "rate_limited"
        assert AdaptiveRetryStrategy.classify("rate_limit exceeded") == "rate_limited"
        assert AdaptiveRetryStrategy.classify("rate limit exceeded") == "rate_limited"
        assert AdaptiveRetryStrategy.classify("too many requests") == "rate_limited"

        assert AdaptiveRetryStrategy.classify("token_rejected") == "token_rejected"
        assert AdaptiveRetryStrategy.classify("human verification failed") == "token_rejected"

        assert AdaptiveRetryStrategy.classify("timeout") == "timeout"
        assert AdaptiveRetryStrategy.classify("connection timed out") == "timeout"

        assert AdaptiveRetryStrategy.classify("503 Service Unavailable") == "server_error"
        assert AdaptiveRetryStrategy.classify("502 Bad Gateway") == "server_error"
        assert AdaptiveRetryStrategy.classify("504 Gateway Timeout") == "server_error"

        assert AdaptiveRetryStrategy.classify("connection refused") == "network_error"
        assert AdaptiveRetryStrategy.classify("connection reset by peer") == "network_error"

        assert AdaptiveRetryStrategy.classify("422 Unprocessable Entity") == "permanent"
        assert AdaptiveRetryStrategy.classify("400 Bad Request") == "permanent"
        assert AdaptiveRetryStrategy.classify("404 Not Found") == "permanent"

    def test_classify_error_types_httpx_response(self) -> None:
        """verify classify works with httpx-like response objects."""

        class MockResponse:
            status_code: int

        class MockError:
            def __init__(self, status_code: int) -> None:
                self.response = MockResponse()
                self.response.status_code = status_code

        assert AdaptiveRetryStrategy.classify(MockError(429)) == "rate_limited"
        assert AdaptiveRetryStrategy.classify(MockError(500)) == "server_error"
        assert AdaptiveRetryStrategy.classify(MockError(502)) == "server_error"
        assert AdaptiveRetryStrategy.classify(MockError(503)) == "server_error"
        assert AdaptiveRetryStrategy.classify(MockError(422)) == "permanent"
        assert AdaptiveRetryStrategy.classify(MockError(404)) == "permanent"
        assert AdaptiveRetryStrategy.classify(MockError(400)) == "permanent"

    def test_classify_error_default(self) -> None:
        """unknown error defaults to timeout (conservative retry)."""
        assert AdaptiveRetryStrategy.classify("unknown weird error") == "timeout"

    def test_should_retry_by_error_type(self) -> None:
        """should_retry respects per-error-type max_retries."""
        # rate_limited: max_retries=5
        for attempt in range(1, 5):
            assert AdaptiveRetryStrategy.should_retry(attempt, 5, "429 rate limited") is True
        assert AdaptiveRetryStrategy.should_retry(5, 5, "429 rate limited") is False

        # timeout: max_retries=3
        for attempt in range(1, 3):
            assert AdaptiveRetryStrategy.should_retry(attempt, 3, "timeout") is True
        assert AdaptiveRetryStrategy.should_retry(3, 3, "timeout") is False

        # network_error: max_retries=2
        assert AdaptiveRetryStrategy.should_retry(1, 2, "connection refused") is True
        assert AdaptiveRetryStrategy.should_retry(2, 2, "connection refused") is False

        # permanent: never retry
        assert AdaptiveRetryStrategy.should_retry(1, 5, "422") is False

    def test_should_retry_passed_max_retries_as_fallback(self) -> None:
        """when error type has no explicit max_retries, use passed max_retries."""
        # classify returns "timeout" for unknown errors, which has max_retries=3
        # unknown error → timeout → max_retries=3
        assert AdaptiveRetryStrategy.should_retry(1, 5, "gibberish error") is True
        assert AdaptiveRetryStrategy.should_retry(3, 5, "gibberish error") is False

    def test_should_retry_zero_attempt(self) -> None:
        """attempt < 1 时不应重试。"""
        assert AdaptiveRetryStrategy.should_retry(0, 3, "timeout") is False

    def test_delay_range(self) -> None:
        """delay 在预期范围内，且有 jitter。"""
        random.seed(42)
        # rate_limited: base=30, jitter=0.5 → attempt 1: [15, 45]
        d = AdaptiveRetryStrategy.delay(1, "rate_limited")
        assert 15 <= d <= 45

        # timeout: base=10, jitter=0.3 → attempt 1: [7, 13]
        random.seed(42)
        d = AdaptiveRetryStrategy.delay(1, "timeout")
        assert 7 <= d <= 13

        # server_error: base=15, jitter=0.4 → attempt 2: [9, 21] * 2 = [18, 42]
        random.seed(42)
        d = AdaptiveRetryStrategy.delay(2, "server_error")
        assert 9 <= d <= 42

    def test_delay_not_deterministic(self) -> None:
        """delay has jitter so values should vary."""
        random.seed(42)
        vals = [AdaptiveRetryStrategy.delay(2, "timeout") for _ in range(10)]
        assert len(set(vals)) > 1, "延迟应因 jitter 而有变化"

    def test_delay_capped_at_max(self) -> None:
        """delay should not exceed MAX_DELAY (300s)."""
        # rate_limited: base=30, attempt 5 → 30 * 16 = 480, capped at 300
        d = AdaptiveRetryStrategy.delay(5, "rate_limited")
        assert d <= 300

        # server_error: base=15, attempt 6 → 15 * 32 = 480, capped at 300
        d = AdaptiveRetryStrategy.delay(6, "server_error")
        assert d <= 300

    def test_delay_unknown_error_type(self) -> None:
        """unknown error type falls back to timeout config."""
        random.seed(42)
        d = AdaptiveRetryStrategy.delay(1, "unknown_type")
        # timeout: base=10, jitter=0.3 → [7, 13]
        assert 7 <= d <= 13

    def test_delay_from_retry_after_none(self) -> None:
        """None returns None."""
        assert AdaptiveRetryStrategy.delay_from_retry_after(None) is None

    def test_delay_from_retry_after_integer(self) -> None:
        """integer string returns float."""
        assert AdaptiveRetryStrategy.delay_from_retry_after("30") == 30.0
        assert AdaptiveRetryStrategy.delay_from_retry_after("120") == 120.0

    def test_delay_from_retry_after_invalid(self) -> None:
        """invalid string returns None."""
        assert AdaptiveRetryStrategy.delay_from_retry_after("foo") is None
        assert AdaptiveRetryStrategy.delay_from_retry_after("") is None

    def test_delay_from_retry_after_http_date(self) -> None:
        """HTTP date format is parsed correctly."""
        # Use a known future date
        future = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(time.time() + 60))
        result = AdaptiveRetryStrategy.delay_from_retry_after(future)
        assert result is not None
        assert 55 <= result <= 65, f"Expected ~60s, got {result}"

    def test_classify_error_compatible(self) -> None:
        """classify_error returns transient/permanent correctly."""
        assert AdaptiveRetryStrategy.classify_error("timeout") == "transient"
        assert AdaptiveRetryStrategy.classify_error("429") == "transient"
        assert AdaptiveRetryStrategy.classify_error("503") == "transient"
        assert AdaptiveRetryStrategy.classify_error("connection refused") == "transient"
        assert AdaptiveRetryStrategy.classify_error("422") == "permanent"
        assert AdaptiveRetryStrategy.classify_error("400") == "permanent"
        assert AdaptiveRetryStrategy.classify_error("404") == "permanent"
        assert AdaptiveRetryStrategy.classify_error("") == "transient"

    def test_backoff_delay_compatible(self) -> None:
        """backoff_delay matches old interface behavior."""
        random.seed(42)
        d = AdaptiveRetryStrategy.backoff_delay(1, 5.0)
        assert 0 <= d <= 5.0

        random.seed(42)
        d2 = AdaptiveRetryStrategy.backoff_delay(2, 5.0)
        assert 0 <= d2 <= 10.0

    def test_retry_policy_alias_exists(self) -> None:
        """RetryPolicy is an alias for AdaptiveRetryStrategy."""
        assert RetryPolicy is AdaptiveRetryStrategy
