# api/imagefree_client.py

- ImagefreeError · class · L33-L34 — class ImagefreeError(RuntimeError)
- _get_client · function · L41-L54 — def _get_client() -> httpx.AsyncClient
- close_client · function · L57-L62 — async def close_client() -> None
- _browser_headers · function · L65-L80 — def _browser_headers(base_url: str, referer: str | None = None) -> dict
- submit_generate · function · L83-L116 — async def submit_generate( base_url: str, prompt: str, aspect_ratio: str, turnstile_token: str, timeout: float = 30.0, ) -> str
- poll_generate_status · function · L119-L164 — async def poll_generate_status( base_url: str, task_id: str, timeout: float = 180.0, poll_interval: float = 2.0, ) -> dict
- download_image · function · L167-L194 — async def download_image( image_url: str, timeout: float = 60.0, max_bytes: int = 4 * 1024 * 1024, ) -> bytes
- to_base64 · function · L197-L199 — def to_base64(data: bytes, mime: str = "image/png") -> str
- detect_mime · function · L202-L214 — def detect_mime(data: bytes) -> str
- _edit_client · function · L227-L232 — async def _edit_client(proxy: str | None) -> httpx.AsyncClient
- upload_edit_image · function · L235-L259 — async def upload_edit_image(base_url: str, image_bytes: bytes, content_type: str = "image/png", timeout: float = 60.0, proxy: str | None = None) -> str
- submit_edit · function · L262-L283 — async def submit_edit(base_url: str, image_url: str, prompt: str, turnstile_token: str, timeout: float = 30.0, proxy: str | None = None) -> str
- poll_edit_status · function · L286-L321 — async def poll_edit_status(base_url: str, task_id: str, timeout: float = 180.0, poll_interval: float = 2.0, proxy: str | None = None) -> dict
