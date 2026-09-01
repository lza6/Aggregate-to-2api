# api/log_buffer.py

- LogBufferHandler · class · L13-L62 — class LogBufferHandler(logging.Handler)
- __init__ · method · L16-L22 — def __init__(self, maxlen: int = 1000) -> None
- emit · method · L24-L52 — def emit(self, record: logging.LogRecord) -> None
- snapshot · method · L54-L56 — def snapshot(self, lines: int = 50) -> list[dict]
- filter_by_trace_id · method · L58-L62 — def filter_by_trace_id(self, trace_id: str, lines: int = 200) -> list[dict]
