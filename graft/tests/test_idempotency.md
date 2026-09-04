# tests/test_idempotency.py

- TestIdempotencyTable · class · L9-L70 — class TestIdempotencyTable
- test_table_exists · method · L13-L19 — async def test_table_exists(self, tmp_db)
- test_save_and_get · method · L22-L30 — async def test_save_and_get(self, tmp_db)
- test_get_nonexistent · method · L33-L36 — async def test_get_nonexistent(self, tmp_db)
- test_overwrite · method · L39-L45 — async def test_overwrite(self, tmp_db)
- test_clean_expired_only · method · L48-L70 — async def test_clean_expired_only(self, tmp_db)
- TestIdempotencyDispatch · class · L74-L117 — class TestIdempotencyDispatch
- enable_idempotency · method · L78-L79 — def enable_idempotency(self, monkeypatch)
- test_known_returns_existing · method · L81-L97 — async def test_known_returns_existing(self, tmp_db, monkeypatch)
- test_without_key_normal · method · L99-L117 — async def test_without_key_normal(self, tmp_db, monkeypatch)
- TestIdempotencyDisabled · class · L120-L134 — class TestIdempotencyDisabled
- disable_idempotency · method · L124-L125 — def disable_idempotency(self, monkeypatch)
- test_db_operations_work · method · L128-L134 — async def test_db_operations_work(self, tmp_db)
- TestClaimIdempotencyAtomic · class · L137-L162 — class TestClaimIdempotencyAtomic
- test_first_claim_wins · method · L141-L144 — async def test_first_claim_wins(self, tmp_db)
- test_second_claim_returns_winner · method · L147-L152 — async def test_second_claim_returns_winner(self, tmp_db)
- test_concurrent_claims_same_key · method · L155-L162 — async def test_concurrent_claims_same_key(self, tmp_db)
