# tests/test_idempotency.py

- TestIdempotencyTable · class · L8-L69 — class TestIdempotencyTable
- test_table_exists · method · L12-L18 — async def test_table_exists(self, tmp_db)
- test_save_and_get · method · L21-L29 — async def test_save_and_get(self, tmp_db)
- test_get_nonexistent · method · L32-L35 — async def test_get_nonexistent(self, tmp_db)
- test_overwrite · method · L38-L44 — async def test_overwrite(self, tmp_db)
- test_clean_expired_only · method · L47-L69 — async def test_clean_expired_only(self, tmp_db)
- TestIdempotencyDispatch · class · L73-L116 — class TestIdempotencyDispatch
- enable_idempotency · method · L77-L78 — def enable_idempotency(self, monkeypatch)
- test_known_returns_existing · method · L80-L96 — async def test_known_returns_existing(self, tmp_db, monkeypatch)
- test_without_key_normal · method · L98-L116 — async def test_without_key_normal(self, tmp_db, monkeypatch)
- TestIdempotencyDisabled · class · L119-L133 — class TestIdempotencyDisabled
- disable_idempotency · method · L123-L124 — def disable_idempotency(self, monkeypatch)
- test_db_operations_work · method · L127-L133 — async def test_db_operations_work(self, tmp_db)
