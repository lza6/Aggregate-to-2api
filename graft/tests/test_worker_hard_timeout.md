# tests/test_worker_hard_timeout.py

- _wait_status · function · L26-L34 — async def _wait_status(db: DB, task_id: str, expected: str, timeout: float = 5.0) -> dict | None
- _clean_db · function · L37-L45 — def _clean_db(path: str) -> None
- _SlowProcessEngine · class · L48-L52 — class _SlowProcessEngine(Engine)
- _process · method · L51-L52 — async def _process(self, task_id: str) -> None
- _FastProcessEngine · class · L55-L59 — class _FastProcessEngine(Engine)
- _process · method · L58-L59 — async def _process(self, task_id: str) -> None
- test_hard_timeout_marks_error · function · L63-L92 — async def test_hard_timeout_marks_error(monkeypatch)
- test_hard_timeout_processing_decremented · function · L96-L125 — async def test_hard_timeout_processing_decremented(monkeypatch)
- test_hard_timeout_upstream_task_id_preserved · function · L129-L164 — async def test_hard_timeout_upstream_task_id_preserved(monkeypatch)
- test_fast_task_not_timed_out · function · L168-L195 — async def test_fast_task_not_timed_out(monkeypatch)
- test_img_task_not_affected · function · L199-L228 — async def test_img_task_not_affected(monkeypatch)
