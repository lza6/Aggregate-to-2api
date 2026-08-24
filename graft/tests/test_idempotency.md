# tests/test_idempotency.py

- TestIdempotencyTable · class · L8-L72 — class TestIdempotencyTable
- test_table_exists · method · L12-L20 — async def test_table_exists(self, tmp_db)
- test_save_and_get · method · L23-L31 — async def test_save_and_get(self, tmp_db)
- test_get_nonexistent · method · L34-L37 — async def test_get_nonexistent(self, tmp_db)
- test_overwrite · method · L40-L46 — async def test_overwrite(self, tmp_db)
- test_clean_expired_only · method · L49-L72 — async def test_clean_expired_only(self, tmp_db)
- TestIdempotencyDispatch · class · L76-L120 — class TestIdempotencyDispatch
- enable_idempotency · method · L80-L81 — def enable_idempotency(self, monkeypatch)
- test_known_returns_existing · method · L83-L100 — async def test_known_returns_existing(self, tmp_db, monkeypatch)
- test_without_key_normal · method · L102-L120 — async def test_without_key_normal(self, tmp_db, monkeypatch)
- TestIdempotencyDisabled · class · L123-L137 — class TestIdempotencyDisabled
- disable_idempotency · method · L127-L128 — def disable_idempotency(self, monkeypatch)
- test_db_operations_work · method · L131-L137 — async def test_db_operations_work(self, tmp_db)
