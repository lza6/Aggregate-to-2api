# api/telemetry.py

- _bool_env · function · L51-L53 — def _bool_env(key: str, default: bool = False) -> bool
- TraceIdLogFilter · class · L56-L74 — class TraceIdLogFilter(logging.Filter)
- filter · method · L63-L74 — def filter(self, record: logging.LogRecord) -> bool
- init_telemetry · function · L77-L138 — def init_telemetry() -> None
- shutdown_telemetry · function · L141-L179 — def shutdown_telemetry() -> None
- get_tracer · function · L182-L186 — def get_tracer(name: str = "imagefree-api")
- is_otel_enabled · function · L189-L191 — def is_otel_enabled() -> bool
- _NoopTracer · class · L194-L198 — class _NoopTracer
- start_as_current_span · method · L197-L198 — def start_as_current_span(self, name: str, **kw)
- _NoopSpanContext · class · L201-L216 — class _NoopSpanContext
- __enter__ · method · L202-L203 — def __enter__(self)
- __exit__ · method · L205-L206 — def __exit__(self, *args)
- set_attribute · method · L208-L209 — def set_attribute(self, k, v)
- add_event · method · L211-L212 — def add_event(self, name: str, attributes=None)
- attributes · method · L215-L216 — def attributes(self)
