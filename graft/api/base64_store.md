# api/base64_store.py

- _mime_to_ext · function · L27-L29 — def _mime_to_ext(mime: str) -> str
- ensure_dir · function · L32-L34 — def ensure_dir() -> str
- _ensure_dir · function · L37-L41 — def _ensure_dir() -> str
- _file_path · function · L44-L48 — def _file_path(task_id: str, mime: str) -> str
- _file_path_from_id · function · L51-L60 — def _file_path_from_id(task_id: str) -> str | None
- save_base64 · function · L63-L79 — def save_base64(task_id: str, data: str, mime: str) -> str
- read_base64 · function · L82-L92 — def read_base64(task_id: str) -> str | None
- delete_base64 · function · L95-L103 — def delete_base64(task_id: str) -> None
- clean_expired · function · L106-L123 — def clean_expired(ttl: float) -> int
- gc_stats · function · L126-L177 — def gc_stats() -> dict
- dir_size_gb · function · L183-L195 — def dir_size_gb(directory: str) -> float
- list_oldest_files · function · L198-L218 — def list_oldest_files(directory: str, n: int | None = None) -> list[str]
- enforce_quota · function · L221-L255 — def enforce_quota(directory: str, max_gb: float, audit_fn=None) -> int
