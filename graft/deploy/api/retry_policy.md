# deploy/api/retry_policy.py

- RetryPolicy · class · L9-L102 — class RetryPolicy
- classify_error · method · L35-L82 — def classify_error(error: object) -> str
- should_retry · method · L85-L92 — def should_retry(attempt: int, max_retries: int, error: object) -> bool
- backoff_delay · method · L95-L102 — def backoff_delay(attempt: int, base_delay: float) -> float
