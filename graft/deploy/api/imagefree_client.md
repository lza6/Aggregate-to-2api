# deploy/api/imagefree_client.py

- ImagefreeError · class · L30-L31 — class ImagefreeError(RuntimeError)
- _get_client · function · L38-L51 — def _get_client() -> httpx.AsyncClient
- close_client · function · L54-L59 — async def close_client() -> None
- _browser_headers · function · L62-L77 — def _browser_headers(base_url: str, referer: str | None = None) -> dict
- submit_generate · function · L80-L113 — async def submit_generate( base_url: str, prompt: str, aspect_ratio: str, turnstile_token: str, timeout: float = 30.0, ) -> str
- poll_generate_status · function · L116-L161 — async def poll_generate_status( base_url: str, task_id: str, timeout: float = 180.0, poll_interval: float = 2.0, ) -> dict
- download_image · function · L164-L180 — async def download_image( image_url: str, timeout: float = 60.0, max_bytes: int = 4 * 1024 * 1024, ) -> bytes
- to_base64 · function · L183-L185 — def to_base64(data: bytes, mime: str = "image/png") -> str
- detect_mime · function · L188-L200 — def detect_mime(data: bytes) -> str
- _edit_client · function · L213-L218 — async def _edit_client(proxy: str | None) -> httpx.AsyncClient
- upload_edit_image · function · L221-L245 — async def upload_edit_image(base_url: str, image_bytes: bytes, content_type: str = "image/png", timeout: float = 60.0, proxy: str | None = None) -> str
- submit_edit · function · L248-L269 — async def submit_edit(base_url: str, image_url: str, prompt: str, turnstile_token: str, timeout: float = 30.0, proxy: str | None = None) -> str
- poll_edit_status · function · L272-L307 — async def poll_edit_status(base_url: str, task_id: str, timeout: float = 180.0, poll_interval: float = 2.0, proxy: str | None = None) -> dict
