# tests/test_cache_persist.py

- tmp_db_path · function · L22-L40 — async def tmp_db_path()
- test_set_persists_to_db · function · L44-L52 — async def test_set_persists_to_db(tmp_db_path)
- test_restore_from_db · function · L56-L71 — async def test_restore_from_db(tmp_db_path)
- test_invalidate_removes_from_db · function · L75-L83 — async def test_invalidate_removes_from_db(tmp_db_path)
- test_invalidate_prefix_removes_from_db · function · L87-L99 — async def test_invalidate_prefix_removes_from_db(tmp_db_path)
- test_flush_all_to_db_on_stop · function · L103-L114 — async def test_flush_all_to_db_on_stop(tmp_db_path)
- test_restore_eliminates_reboot_gap · function · L118-L129 — async def test_restore_eliminates_reboot_gap(tmp_db_path)
- test_no_persist_mode_works · function · L133-L140 — async def test_no_persist_mode_works(tmp_db_path)
- test_evicted_item_persisted · function · L144-L153 — async def test_evicted_item_persisted(tmp_db_path)
- test_serialize_deserialize_roundtrip · function · L157-L171 — async def test_serialize_deserialize_roundtrip(tmp_db_path)
- test_snapshot_with_persist · function · L175-L184 — async def test_snapshot_with_persist(tmp_db_path)
