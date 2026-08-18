# tests/test_worker_hard_timeout.py

- _clean_db · function · L21-L29 — def _clean_db(path: str) -> None
- _SlowProcessEngine · class · L32-L36 — class _SlowProcessEngine(Engine)
- _process · method · L35-L36 — async def _process(self, task_id: str) -> None
- _FastProcessEngine · class · L39-L43 — class _FastProcessEngine(Engine)
- _process · method · L42-L43 — async def _process(self, task_id: str) -> None
- test_hard_timeout_marks_error · function · L47-L76 — async def test_hard_timeout_marks_error()
- test_hard_timeout_processing_decremented · function · L80-L103 — async def test_hard_timeout_processing_decremented()
- test_hard_timeout_upstream_task_id_preserved · function · L107-L138 — async def test_hard_timeout_upstream_task_id_preserved()
- test_fast_task_not_timed_out · function · L142-L166 — async def test_fast_task_not_timed_out()
- test_img_task_not_affected · function · L170-L195 — async def test_img_task_not_affected()
