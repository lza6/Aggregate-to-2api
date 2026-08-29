# deploy/api/log_buffer.py

- LogBufferHandler · class · L8-L33 — class LogBufferHandler(logging.Handler)
- __init__ · method · L11-L17 — def __init__(self, maxlen: int = 1000) -> None
- emit · method · L19-L29 — def emit(self, record: logging.LogRecord) -> None
- snapshot · method · L31-L33 — def snapshot(self, lines: int = 50) -> list[dict]
