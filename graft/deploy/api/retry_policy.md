# deploy/api/retry_policy.py

- AdaptiveRetryStrategy · class · L12-L198 — class AdaptiveRetryStrategy
- classify · method · L37-L109 — def classify(error: object) -> str
- should_retry · method · L112-L131 — def should_retry(attempt: int, max_retries: int, error: object) -> bool
- delay · method · L134-L151 — def delay(attempt: int, error_type: str) -> float
- delay_from_retry_after · method · L154-L181 — def delay_from_retry_after(header_value: str | None) -> float | None
- classify_error · method · L186-L189 — def classify_error(error: object) -> str
- backoff_delay · method · L192-L198 — def backoff_delay(attempt: int, base_delay: float) -> float
