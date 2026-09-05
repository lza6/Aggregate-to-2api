"""tests/test_retry_policy_kinds.py — P1-A5（M11）失败分类加 kind 测试。

验收：
- 413 归类为 payload_too_large（不重试）
- 401/403 归类为 forbidden（不重试）
- should_retry 对 forbidden/payload_too_large 返回 False
- classify_error 对 forbidden/payload_too_large 返回 permanent
- Retry-After 头解析（秒数 + HTTP 日期）
"""

from __future__ import annotations


class _FakeResp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeErr(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.response = _FakeResp(status_code)


def test_classify_payload_too_large():
    """413 归类为 payload_too_large。"""
    from api.retry_policy import AdaptiveRetryStrategy

    assert AdaptiveRetryStrategy.classify(_FakeErr("too large", status_code=413)) == "payload_too_large"


def test_classify_forbidden_403():
    """403 归类为 forbidden。"""
    from api.retry_policy import AdaptiveRetryStrategy

    assert AdaptiveRetryStrategy.classify(_FakeErr("forbidden", status_code=403)) == "forbidden"


def test_classify_forbidden_401():
    """401 归类为 forbidden。"""
    from api.retry_policy import AdaptiveRetryStrategy

    assert AdaptiveRetryStrategy.classify(_FakeErr("unauthorized", status_code=401)) == "forbidden"


def test_should_retry_forbidden_false():
    """forbidden 不重试。"""
    from api.retry_policy import AdaptiveRetryStrategy

    err = _FakeErr("forbidden", status_code=403)
    assert AdaptiveRetryStrategy.should_retry(1, 3, err) is False


def test_should_retry_payload_too_large_false():
    """payload_too_large 不重试。"""
    from api.retry_policy import AdaptiveRetryStrategy

    err = _FakeErr("too large", status_code=413)
    assert AdaptiveRetryStrategy.should_retry(1, 3, err) is False


def test_classify_error_forbidden_permanent():
    """classify_error 对 forbidden 返回 permanent。"""
    from api.retry_policy import AdaptiveRetryStrategy

    err = _FakeErr("forbidden", status_code=403)
    assert AdaptiveRetryStrategy.classify_error(err) == "permanent"


def test_classify_error_payload_too_large_permanent():
    """classify_error 对 payload_too_large 返回 permanent。"""
    from api.retry_policy import AdaptiveRetryStrategy

    err = _FakeErr("too large", status_code=413)
    assert AdaptiveRetryStrategy.classify_error(err) == "permanent"


def test_payload_too_large_markers():
    """消息标记匹配 payload_too_large。"""
    from api.retry_policy import AdaptiveRetryStrategy

    assert AdaptiveRetryStrategy.classify(_FakeErr("413 Request Entity Too Large")) == "payload_too_large"
    assert AdaptiveRetryStrategy.classify(_FakeErr("payload too large")) == "payload_too_large"


def test_delay_from_retry_after_seconds():
    """Retry-After 头解析秒数。"""
    from api.retry_policy import AdaptiveRetryStrategy

    assert AdaptiveRetryStrategy.delay_from_retry_after("60") == 60.0
    assert AdaptiveRetryStrategy.delay_from_retry_after("0") == 0.0


def test_delay_from_retry_after_none():
    """Retry-After 头为 None/空 → None。"""
    from api.retry_policy import AdaptiveRetryStrategy

    assert AdaptiveRetryStrategy.delay_from_retry_after(None) is None
    assert AdaptiveRetryStrategy.delay_from_retry_after("") is None
    assert AdaptiveRetryStrategy.delay_from_retry_after("   ") is None


def test_delay_from_retry_after_http_date():
    """Retry-After 头 HTTP 日期格式解析。"""
    from api.retry_policy import AdaptiveRetryStrategy

    # HTTP 日期格式（RFC 7231）
    secs = AdaptiveRetryStrategy.delay_from_retry_after("Wed, 21 Oct 2099 07:28:00 GMT")
    assert secs is not None
    assert secs >= 0


def test_rate_limited_still_works():
    """429 仍归类为 rate_limited（回归保护）。"""
    from api.retry_policy import AdaptiveRetryStrategy

    assert AdaptiveRetryStrategy.classify(_FakeErr("rate limit", status_code=429)) == "rate_limited"
