# api/telemetry.py

- _bool_env · function · L53-L55 — def _bool_env(key: str, default: bool = False) -> bool
- TraceIdLogFilter · class · L58-L76 — class TraceIdLogFilter(logging.Filter)
- filter · method · L65-L76 — def filter(self, record: logging.LogRecord) -> bool
- init_telemetry · function · L79-L154 — def init_telemetry() -> None
- shutdown_telemetry · function · L157-L195 — def shutdown_telemetry() -> None
- get_tracer · function · L198-L202 — def get_tracer(name: str = "imagefree-api")
- is_otel_enabled · function · L205-L207 — def is_otel_enabled() -> bool
- _NoopTracer · class · L210-L214 — class _NoopTracer
- start_as_current_span · method · L213-L214 — def start_as_current_span(self, name: str, **kw)
- _NoopSpanContext · class · L217-L232 — class _NoopSpanContext
- __enter__ · method · L218-L219 — def __enter__(self)
- __exit__ · method · L221-L222 — def __exit__(self, *args)
- set_attribute · method · L224-L225 — def set_attribute(self, k, v)
- add_event · method · L227-L228 — def add_event(self, name: str, attributes=None)
- attributes · method · L231-L232 — def attributes(self)
