# api/log_buffer.py

- LogBufferHandler · class · L9-L34 — class LogBufferHandler(logging.Handler)
- __init__ · method · L12-L18 — def __init__(self, maxlen: int = 1000) -> None
- emit · method · L20-L30 — def emit(self, record: logging.LogRecord) -> None
- snapshot · method · L32-L34 — def snapshot(self, lines: int = 50) -> list[dict]
