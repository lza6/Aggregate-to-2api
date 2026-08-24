# deploy/api/base64_store.py

- _mime_to_ext · function · L26-L28 — def _mime_to_ext(mime: str) -> str
- ensure_dir · function · L31-L33 — def ensure_dir() -> str
- _ensure_dir · function · L36-L40 — def _ensure_dir() -> str
- _file_path · function · L43-L47 — def _file_path(task_id: str, mime: str) -> str
- _file_path_from_id · function · L50-L59 — def _file_path_from_id(task_id: str) -> str | None
- save_base64 · function · L62-L78 — def save_base64(task_id: str, data: str, mime: str) -> str
- read_base64 · function · L81-L91 — def read_base64(task_id: str) -> str | None
- delete_base64 · function · L94-L102 — def delete_base64(task_id: str) -> None
- clean_expired · function · L105-L122 — def clean_expired(ttl: float) -> int
- dir_size_gb · function · L128-L140 — def dir_size_gb(directory: str) -> float
- list_oldest_files · function · L143-L163 — def list_oldest_files(directory: str, n: int | None = None) -> list[str]
- enforce_quota · function · L166-L203 — def enforce_quota(directory: str, max_gb: float, audit_fn=None) -> int
