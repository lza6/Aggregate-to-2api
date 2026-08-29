# api/retry_policy.py

- AdaptiveRetryStrategy · class · L11-L196 — class AdaptiveRetryStrategy
- classify · method · L37-L106 — def classify(error: object) -> str
- should_retry · method · L109-L129 — def should_retry(attempt: int, max_retries: int, error: object) -> bool
- delay · method · L132-L149 — def delay(attempt: int, error_type: str) -> float
- delay_from_retry_after · method · L152-L179 — def delay_from_retry_after(header_value: str | None) -> float | None
- classify_error · method · L184-L187 — def classify_error(error: object) -> str
- backoff_delay · method · L190-L196 — def backoff_delay(attempt: int, base_delay: float) -> float
