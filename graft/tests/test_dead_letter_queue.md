# tests/test_dead_letter_queue.py

- TestDeadLetterQueueDB · class · L15-L77 — class TestDeadLetterQueueDB
- test_push_and_list_dlq · method · L18-L25 — def test_push_and_list_dlq(self, tmp_db: DB)
- test_list_dlq_limit · method · L27-L32 — def test_list_dlq_limit(self, tmp_db: DB)
- test_list_dlq_ordered_by_created_at · method · L34-L44 — def test_list_dlq_ordered_by_created_at(self, tmp_db: DB)
- test_retry_dlq · method · L46-L51 — def test_retry_dlq(self, tmp_db: DB)
- test_clear_dlq · method · L53-L59 — def test_clear_dlq(self, tmp_db: DB)
- test_retry_nonexistent · method · L61-L63 — def test_retry_nonexistent(self, tmp_db: DB)
- test_clear_empty · method · L65-L67 — def test_clear_empty(self, tmp_db: DB)
- test_push_dlq_duplicate_task_id · method · L69-L77 — def test_push_dlq_duplicate_task_id(self, tmp_db: DB)
- TestDeadLetterQueueWorker · class · L80-L139 — class TestDeadLetterQueueWorker
- test_worker_pushes_dlq_on_retry_exhaustion · method · L84-L112 — async def test_worker_pushes_dlq_on_retry_exhaustion(self, tmp_db, monkeypatch)
- _solve · function · L90-L91 — async def _solve(*a, **k)
- _submit · function · L94-L95 — async def _submit(*a, **k)
- test_worker_skip_dlq_when_disabled · method · L115-L139 — async def test_worker_skip_dlq_when_disabled(self, tmp_db, monkeypatch)
- _solve · function · L120-L121 — async def _solve(*a, **k)
- _submit · function · L123-L124 — async def _submit(*a, **k)
