# tests/test_cache_persist.py

- tmp_db_path · function · L21-L35 — def tmp_db_path()
- test_set_persists_to_db · function · L39-L47 — async def test_set_persists_to_db(tmp_db_path)
- test_restore_from_db · function · L51-L66 — async def test_restore_from_db(tmp_db_path)
- test_invalidate_removes_from_db · function · L70-L78 — async def test_invalidate_removes_from_db(tmp_db_path)
- test_invalidate_prefix_removes_from_db · function · L82-L94 — async def test_invalidate_prefix_removes_from_db(tmp_db_path)
- test_flush_all_to_db_on_stop · function · L98-L109 — async def test_flush_all_to_db_on_stop(tmp_db_path)
- test_restore_eliminates_reboot_gap · function · L113-L124 — async def test_restore_eliminates_reboot_gap(tmp_db_path)
- test_no_persist_mode_works · function · L128-L135 — async def test_no_persist_mode_works(tmp_db_path)
- test_evicted_item_persisted · function · L139-L148 — async def test_evicted_item_persisted(tmp_db_path)
- test_serialize_deserialize_roundtrip · function · L152-L166 — async def test_serialize_deserialize_roundtrip(tmp_db_path)
- test_snapshot_with_persist · function · L170-L179 — async def test_snapshot_with_persist(tmp_db_path)
