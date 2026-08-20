"""OpenTelemetry 追踪初始化：trace_id 贯穿请求全生命周期（IMP-08）。

提供三种 instrumentation：
1. FastAPIInstrumentor — 自动捕获 HTTP 请求→响应 span
2. HTTPXClientInstrumentor — 自动捕获上游 HTTP 调用 span（imagefree.net / cf_solver）
3. LoggingInstrumentor — 日志记录自动注入 trace_id

配置（环境变量）：
  IF_OTEL_ENABLED=1                 启用 OTel（默认 0=关闭，兼容旧行为）
  IF_OTEL_SERVICE_NAME              服务名（默认 "imagefree-api"）
  IF_OTEL_EXPORTER_OTLP_ENDPOINT    OTLP gRPC 导出目标（默认空=仅控制台输出）

用法：在 lifespan 中调用 init_telemetry()，关闭时调用 shutdown_telemetry()。
"""
from __future__ import annotations

import logging
import os

from . import config as app_config

log = logging.getLogger("telemetry")

# ── 安全导入：opentelemetry 包未安装时降级（零开销）───────
_OTEL_AVAILABLE = False
_FastAPIInstrumentor = None
_HTTPXClientInstrumentor = None
_LoggingInstrumentor = None
_trace = None
try:
    from opentelemetry import trace as _trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor as _F
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor as _H
    from opentelemetry.instrumentation.logging import LoggingInstrumentor as _L
    _FastAPIInstrumentor = _F
    _HTTPXClientInstrumentor = _H
    _LoggingInstrumentor = _L
    _OTEL_AVAILABLE = True
except ImportError:
    pass

# 模块级变量，供 lifespan 控制生命周期
_otel_enabled = False
_tracer_provider: object | None = None


def _bool_env(key: str, default: bool = False) -> bool:
    val = os.getenv(key, "1" if default else "0")
    return val.strip().lower() in {"1", "true", "yes", "on"}


class TraceIdLogFilter(logging.Filter):
    """向日志消息追加 trace_id 片段（当 OTel 激活且有当前 span 时）。

    效果：每条日志末尾追加 [trace=<hex_id>]，无活跃 span 时不追加。
    不修改日志格式，仅追加到 message 末尾。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not _otel_enabled or not _trace:
            return True
        try:
            span = _trace.get_current_span()
            sc = span.get_span_context()
            if sc and sc.trace_id != 0x0:
                tid = format(sc.trace_id, "032x")[:16]
                record.msg = f"{record.msg} [trace={tid}]"
        except Exception:
            pass
        return True


def init_telemetry() -> None:
    """初始化 OTel SDK，由 lifespan 调用。IF_OTEL_ENABLED=0 或包缺失时无操作。

    幂等：已初始化时二次调用不重复 init。
    """
    global _otel_enabled, _tracer_provider
    if _otel_enabled:
        return
    if not _OTEL_AVAILABLE:
        log.info("OTel 包未安装，跳过追踪初始化")
        return
    # 实时读 env（A-02 后 config 缓存了 import 时的值；测试/运行时改 env 需生效）
    if os.getenv("IF_OTEL_ENABLED", "1" if app_config.OTEL_ENABLED else "0").strip().lower() not in {"1", "true", "yes", "on"}:
        log.info("OTel 未启用（IF_OTEL_ENABLED=0），跳过追踪初始化")
        return

    service_name = os.getenv("IF_OTEL_SERVICE_NAME", app_config.OTEL_SERVICE_NAME)
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    # Console 导出器（调试用，需显式设置 IF_OTEL_CONSOLE_EXPORTER=1）
    if os.getenv("IF_OTEL_CONSOLE_EXPORTER", "1" if app_config.OTEL_CONSOLE_EXPORTER else "0").strip().lower() in {"1", "true", "yes", "on"}:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # OTLP 导出器（生产环境对接上游追踪系统如 Jaeger、Tempo）
    otlp_endpoint = os.getenv("IF_OTEL_EXPORTER_OTLP_ENDPOINT", app_config.OTEL_EXPORTER_OTLP_ENDPOINT or "") or ""
    if otlp_endpoint:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            log.info("OTel OTLP 导出已配置: %s", otlp_endpoint)
        except Exception as e:
            log.warning("OTLPSpanExporter 初始化失败（仅控制台输出）: %s", e)

    _trace.set_tracer_provider(provider)
    _tracer_provider = provider

    # FastAPI：自动捕获 HTTP 请求→响应 span
    try:
        _FastAPIInstrumentor().instrument()
    except Exception:
        log.warning("FastAPIInstrumentor 已 instrument 或初始化失败，跳过")
    # httpx：自动捕获上游 HTTP 调用 span
    try:
        _HTTPXClientInstrumentor().instrument()
    except Exception:
        log.warning("HTTPXClientInstrumentor 已 instrument 或初始化失败，跳过")
    # logging：注入 otelTraceID / otelSpanID 到 LogRecord
    try:
        _LoggingInstrumentor().instrument(set_logging_format=False)
    except Exception:
        log.warning("LoggingInstrumentor 已 instrument 或初始化失败，跳过")

    # 为 root logger 添加 TraceIdLogFilter，使每条日志末尾带 trace_id
    root_logger = logging.getLogger()
    has_filter = any(isinstance(f, TraceIdLogFilter) for f in root_logger.filters)
    if not has_filter:
        root_logger.addFilter(TraceIdLogFilter())

    _otel_enabled = True
    log.info("OTel 追踪已初始化（service=%s, exporter=%s, otel=%s）",
             service_name, otlp_endpoint or "console", _OTEL_AVAILABLE)


def shutdown_telemetry() -> None:
    """关闭 OTel 追踪：Flush + 反注册 Instrumentation。

    由 lifespan 的 shutdown 阶段调用，确保 span 不丢失。幂等，可多次调用。
    """
    global _otel_enabled, _tracer_provider
    if not _otel_enabled or not _tracer_provider:
        return
    # 移除 TraceIdLogFilter
    root_logger = logging.getLogger()
    root_logger.filters = [f for f in root_logger.filters if not isinstance(f, TraceIdLogFilter)]

    # 反注册 instrumentations（忽略已卸载的异常）
    if _FastAPIInstrumentor:
        try:
            _FastAPIInstrumentor().uninstrument()
        except Exception:
            pass
    if _HTTPXClientInstrumentor:
        try:
            _HTTPXClientInstrumentor().uninstrument()
        except Exception:
            pass
    if _LoggingInstrumentor:
        try:
            _LoggingInstrumentor().uninstrument()
        except Exception:
            pass

    try:
        _tracer_provider.force_flush()  # type: ignore[union-attr]
    except Exception:
        pass
    try:
        _tracer_provider.shutdown()  # type: ignore[union-attr]
    except Exception:
        pass
    _otel_enabled = False
    log.info("OTel 追踪已关闭")


def get_tracer(name: str = "imagefree-api"):
    """获取命名 tracer，供需要手动创建 span 的模块使用。OTel 未启用时返回 no-op tracer。"""
    if _otel_enabled and _trace:
        return _trace.get_tracer(name)
    return _NoopTracer()


def is_otel_enabled() -> bool:
    """当前 OTel 是否已启用。"""
    return _otel_enabled


class _NoopTracer:
    """OTel 未启用时使用的 no-op tracer，避免 NPE。"""

    def start_as_current_span(self, name: str, **kw):
        return _NoopSpanContext()


class _NoopSpanContext:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def set_attribute(self, k, v):
        pass

    def add_event(self, name: str, attributes=None):
        pass

    @property
    def attributes(self):
        return {}