# deploy/api/retry_policy.py

- AdaptiveRetryStrategy · class · L11-L192 — class AdaptiveRetryStrategy
- classify · method · L36-L102 — def classify(error: object) -> str
- should_retry · method · L105-L125 — def should_retry(attempt: int, max_retries: int, error: object) -> bool
- delay · method · L128-L145 — def delay(attempt: int, error_type: str) -> float
- delay_from_retry_after · method · L148-L175 — def delay_from_retry_after(header_value: str | None) -> float | None
- classify_error · method · L180-L183 — def classify_error(error: object) -> str
- backoff_delay · method · L186-L192 — def backoff_delay(attempt: int, base_delay: float) -> float
