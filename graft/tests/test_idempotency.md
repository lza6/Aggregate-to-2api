# tests/test_idempotency.py

- TestIdempotencyTable · class · L8-L63 — class TestIdempotencyTable
- test_table_exists · method · L11-L18 — def test_table_exists(self, tmp_db)
- test_save_and_get · method · L20-L28 — def test_save_and_get(self, tmp_db)
- test_get_nonexistent · method · L30-L32 — def test_get_nonexistent(self, tmp_db)
- test_overwrite · method · L34-L40 — def test_overwrite(self, tmp_db)
- test_clean_expired_only · method · L42-L63 — def test_clean_expired_only(self, tmp_db)
- TestIdempotencyDispatch · class · L67-L109 — class TestIdempotencyDispatch
- enable_idempotency · method · L71-L72 — def enable_idempotency(self, monkeypatch)
- test_known_returns_existing · method · L74-L90 — async def test_known_returns_existing(self, tmp_db, monkeypatch)
- test_without_key_normal · method · L92-L109 — async def test_without_key_normal(self, tmp_db, monkeypatch)
- TestIdempotencyDisabled · class · L112-L125 — class TestIdempotencyDisabled
- disable_idempotency · method · L116-L117 — def disable_idempotency(self, monkeypatch)
- test_db_operations_work · method · L119-L125 — def test_db_operations_work(self, tmp_db)
