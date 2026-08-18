# tests/test_account_pool.py

- _FakeReg · class · L14-L24 — class _FakeReg
- register_one · method · L18-L21 — async def register_one(self)
- checkin · method · L23-L24 — async def checkin(self, acc)
- pool · function · L28-L36 — def pool(tmp_path)
- TestAccountPool · class · L40-L69 — class TestAccountPool
- test_add_and_get · method · L41-L49 — def test_add_and_get(self, pool)
- test_mark_and_credits · method · L51-L56 — def test_mark_and_credits(self, pool)
- test_counts · method · L58-L63 — def test_counts(self, pool)
- test_dashboard · method · L65-L69 — def test_dashboard(self, pool)
- test_autoregister_loop_fills_to_target · function · L74-L99 — async def test_autoregister_loop_fills_to_target(tmp_path, monkeypatch)
- test_daily_checkin_updates_credits · function · L104-L121 — async def test_daily_checkin_updates_credits(tmp_path)
- _checkin · function · L111-L112 — async def _checkin(acc)
- TestEmailPool · class · L125-L150 — class TestEmailPool
- test_allocate_unique_and_record · method · L127-L139 — async def test_allocate_unique_and_record(self, tmp_path)
- test_stats · method · L142-L150 — async def test_stats(self, tmp_path)
