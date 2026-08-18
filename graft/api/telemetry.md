# api/telemetry.py

- _bool_env · function · L49-L51 — def _bool_env(key: str, default: bool = False) -> bool
- TraceIdLogFilter · class · L54-L72 — class TraceIdLogFilter(logging.Filter)
- filter · method · L61-L72 — def filter(self, record: logging.LogRecord) -> bool
- init_telemetry · function · L75-L135 — def init_telemetry() -> None
- shutdown_telemetry · function · L138-L176 — def shutdown_telemetry() -> None
- get_tracer · function · L179-L183 — def get_tracer(name: str = "imagefree-api")
- is_otel_enabled · function · L186-L188 — def is_otel_enabled() -> bool
- _NoopTracer · class · L191-L195 — class _NoopTracer
- start_as_current_span · method · L194-L195 — def start_as_current_span(self, name: str, **kw)
- _NoopSpanContext · class · L198-L213 — class _NoopSpanContext
- __enter__ · method · L199-L200 — def __enter__(self)
- __exit__ · method · L202-L203 — def __exit__(self, *args)
- set_attribute · method · L205-L206 — def set_attribute(self, k, v)
- add_event · method · L208-L209 — def add_event(self, name: str, attributes=None)
- attributes · method · L212-L213 — def attributes(self)
