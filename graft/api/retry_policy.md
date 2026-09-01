# api/retry_policy.py

- AdaptiveRetryStrategy · class · L12-L197 — class AdaptiveRetryStrategy
- classify · method · L38-L107 — def classify(error: object) -> str
- should_retry · method · L110-L130 — def should_retry(attempt: int, max_retries: int, error: object) -> bool
- delay · method · L133-L150 — def delay(attempt: int, error_type: str) -> float
- delay_from_retry_after · method · L153-L180 — def delay_from_retry_after(header_value: str | None) -> float | None
- classify_error · method · L185-L188 — def classify_error(error: object) -> str
- backoff_delay · method · L191-L197 — def backoff_delay(attempt: int, base_delay: float) -> float
