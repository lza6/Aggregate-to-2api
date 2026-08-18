# api/telemetry.py

- _bool_env · function · L44-L46 — def _bool_env(key: str, default: bool = False) -> bool
- TraceIdLogFilter · class · L49-L67 — class TraceIdLogFilter(logging.Filter)
- filter · method · L56-L67 — def filter(self, record: logging.LogRecord) -> bool
- init_telemetry · function · L70-L117 — def init_telemetry() -> None
- shutdown_telemetry · function · L120-L154 — def shutdown_telemetry() -> None
- get_tracer · function · L157-L161 — def get_tracer(name: str = "imagefree-api") -> "trace.Tracer"
- _NoopTracer · class · L164-L168 — class _NoopTracer
- start_as_current_span · method · L167-L168 — def start_as_current_span(self, name: str, **kw)
- _NoopSpanContext · class · L171-L183 — class _NoopSpanContext
- __enter__ · method · L172-L173 — def __enter__(self)
- __exit__ · method · L175-L176 — def __exit__(self, *args)
- set_attribute · method · L178-L179 — def set_attribute(self, k, v)
- attributes · method · L182-L183 — def attributes(self)
- is_otel_enabled · function · L186-L188 — def is_otel_enabled() -> bool
