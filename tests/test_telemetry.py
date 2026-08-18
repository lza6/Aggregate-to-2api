"""IMP-08: OpenTelemetry 追踪 E2E 测试。

验证：
1. init_telemetry / shutdown_telemetry 生命周期（幂等、启用/关闭）
2. IF_OTEL_ENABLED=0 时零开销
3. TraceIdLogFilter 日志注入 trace_id
4. 自定义 span 创建（get_tracer）
5. 模块导入 / 公开 API 完整
6. noop tracer 安全降级
"""
import logging
import os

import pytest


# ============================================================
# 生命周期
# ============================================================
class TestTelemetryLifecycle:
    def test_disabled_when_env_not_set(self):
        """IF_OTEL_ENABLED=0 时不初始化 OTel，零开销。"""
        os.environ["IF_OTEL_ENABLED"] = "0"
        from api.telemetry import (
            _otel_enabled,
            init_telemetry,
            is_otel_enabled,
            shutdown_telemetry,
        )

        init_telemetry()
        assert not _otel_enabled
        assert not is_otel_enabled()
        # 关闭不报错
        shutdown_telemetry()

    def test_enabled_with_env(self):
        """IF_OTEL_ENABLED=1 时正确初始化。"""
        os.environ["IF_OTEL_ENABLED"] = "1"
        os.environ["IF_OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
        import api.telemetry

        api.telemetry.init_telemetry()
        assert api.telemetry._otel_enabled
        assert api.telemetry.is_otel_enabled()
        api.telemetry.shutdown_telemetry()
        # 关闭后重置
        assert not api.telemetry.is_otel_enabled()
        assert not api.telemetry._otel_enabled

    def test_double_init_shutdown_no_error(self):
        """重复 init/shutdown 不报错（幂等）。"""
        os.environ["IF_OTEL_ENABLED"] = "1"
        from api.telemetry import init_telemetry, shutdown_telemetry

        init_telemetry()
        init_telemetry()  # 二次 init 不挂
        shutdown_telemetry()
        shutdown_telemetry()  # 二次 shutdown 不挂

    def test_missing_package_graceful(self):
        """opentelemetry 包不可用时静默降级。"""
        os.environ["IF_OTEL_ENABLED"] = "1"
        from api.telemetry import _OTEL_AVAILABLE, init_telemetry, is_otel_enabled

        # 包可用时，直接测试 init 行为
        # 如果包确实不可用，init 应静默跳过
        init_telemetry()
        assert is_otel_enabled() == _OTEL_AVAILABLE

    def test_disabled_then_enabled(self):
        """先关后开，状态正确切换。"""
        os.environ["IF_OTEL_ENABLED"] = "0"
        from api.telemetry import init_telemetry, is_otel_enabled, shutdown_telemetry

        init_telemetry()
        assert not is_otel_enabled()
        shutdown_telemetry()

        os.environ["IF_OTEL_ENABLED"] = "1"
        init_telemetry()
        enabled = is_otel_enabled()
        # 清理
        shutdown_telemetry()
        os.environ["IF_OTEL_ENABLED"] = "0"
        assert enabled  # 第二次 init 应成功


# ============================================================
# TraceIdLogFilter
# ============================================================
class TestTraceIdLogFilter:
    def test_filter_available(self):
        """TraceIdLogFilter 是 logging.Filter 子类。"""
        from api.telemetry import TraceIdLogFilter

        assert issubclass(TraceIdLogFilter, logging.Filter)
        f = TraceIdLogFilter()
        assert isinstance(f, logging.Filter)

    def test_filter_noop_when_otel_disabled(self):
        """OTel 未启用时 filter 不修改消息。"""
        os.environ["IF_OTEL_ENABLED"] = "0"
        from api.telemetry import TraceIdLogFilter

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        f = TraceIdLogFilter()
        f.filter(record)
        assert record.msg == "hello world"

    def test_filter_noop_when_no_active_span(self):
        """无活跃 span 时 filter 不修改消息。"""
        os.environ["IF_OTEL_ENABLED"] = "1"
        os.environ["IF_OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
        from api.telemetry import init_telemetry, shutdown_telemetry

        init_telemetry()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        from api.telemetry import TraceIdLogFilter

        f = TraceIdLogFilter()
        f.filter(record)
        assert record.msg == "hello world"
        shutdown_telemetry()

    def test_filter_appends_trace_id_when_otel_active(self):
        """OTel 启用且有活跃 span 时，日志消息末尾追加 [trace=<hex>]。"""
        os.environ["IF_OTEL_ENABLED"] = "1"
        os.environ["IF_OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
        from api.telemetry import init_telemetry, shutdown_telemetry

        init_telemetry()
        from api.telemetry import _trace

        tracer = _trace.get_tracer("test")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        with tracer.start_as_current_span("test-span"):
            from api.telemetry import TraceIdLogFilter

            f = TraceIdLogFilter()
            f.filter(record)
            assert "[trace=" in record.msg
            tid = record.msg.split("[trace=")[1].split("]")[0]
            assert len(tid) == 16
            assert all(c in "0123456789abcdef" for c in tid)
        shutdown_telemetry()


# ============================================================
# 自定义 span 创建
# ============================================================
class TestCustomSpans:
    def test_get_tracer_returns_tracer(self):
        """get_tracer() 返回可用 tracer（OTel 启用时返回真实 tracer）。"""
        os.environ["IF_OTEL_ENABLED"] = "1"
        os.environ["IF_OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
        from api.telemetry import (
            _otel_enabled,
            get_tracer,
            init_telemetry,
            shutdown_telemetry,
        )

        init_telemetry()
        if _otel_enabled:
            tracer = get_tracer("test")
            assert tracer is not None
            # 创建 span 不抛异常
            with tracer.start_as_current_span("test-span") as span:
                span.set_attribute("test.key", "test.value")
        shutdown_telemetry()

    def test_get_tracer_noop_when_disabled(self):
        """OTel 关闭时 get_tracer() 返回 noop tracer，不抛异常。"""
        os.environ["IF_OTEL_ENABLED"] = "0"
        from api.telemetry import get_tracer

        tracer = get_tracer("test")
        with tracer.start_as_current_span("test-span") as span:
            span.set_attribute("test.key", "test.value")
        # 不抛异常即成功

    def test_is_otel_enabled_reflects_state(self):
        """is_otel_enabled() 反映当前启用状态。"""
        os.environ["IF_OTEL_ENABLED"] = "1"
        os.environ["IF_OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
        from api.telemetry import (
            init_telemetry,
            is_otel_enabled,
            shutdown_telemetry,
        )

        init_telemetry()
        if is_otel_enabled():
            shutdown_telemetry()
            assert not is_otel_enabled()
        else:
            # 包不可用时，始终返回 False
            assert not is_otel_enabled()


# ============================================================
# worker 自定义 span 集成测试
# ============================================================
class TestWorkerSpan:
    def test_worker_process_span_attributes(self):
        """worker._process 的 span 属性可正确设置。"""
        import api.telemetry

        tracer = api.telemetry.get_tracer()
        import uuid

        tid = uuid.uuid4().hex
        with tracer.start_as_current_span(
            "worker.process",
            attributes={
                "task.id": tid,
                "task.prompt_preview": "test prompt",
                "task.model": "default",
                "task.aspect_ratio": "1:1",
            },
        ):
            pass  # span 创建不抛异常即验证通过
        # 验证 noop span 的 attributes 为 empty dict
        # 真实 span 的 attributes 由 OTel SDK 管理，此处仅验证接口兼容
            assert attrs["task.model"] == "default"


# ============================================================
# turnstile_client 自定义 span 集成测试
# ============================================================
class TestTurnstileSpan:
    def test_solve_turnstile_span_attributes(self):
        """solve_turnstile 的 span 含正确属性。"""
        import api.telemetry

        tracer = api.telemetry.get_tracer()
        with tracer.start_as_current_span(
            "turnstile.solve",
            attributes={
                "cf_solver.url": "http://localhost:8001",
                "target.url": "https://imagefree.net",
                "sitekey": "0x4AAAA...",
                "proxy": "no",
            },
        ) as span:
            attrs = span.attributes
            if api.telemetry.is_otel_enabled():
                assert attrs["cf_solver.url"] == "http://localhost:8001"
            else:
                assert attrs == {}


# ============================================================
# 快照/断言测试
# ============================================================
class TestTelemetrySnapshot:
    def test_telemetry_module_importable(self):
        """telemetry 模块可导入。"""
        from api import telemetry

        assert telemetry.__doc__ is not None

    def test_all_public_api_exists(self):
        """公开 API 全部存在。"""
        from api.telemetry import (
            TraceIdLogFilter,
            get_tracer,
            init_telemetry,
            is_otel_enabled,
            shutdown_telemetry,
        )

        assert callable(init_telemetry)
        assert callable(shutdown_telemetry)
        assert callable(get_tracer)
        assert callable(is_otel_enabled)
        assert issubclass(TraceIdLogFilter, logging.Filter)

    def test_main_module_imports_telemetry(self):
        """main.py 正确导入 telemetry 模块。"""
        from api.main import lifespan

        # lifespan 引用了 init_telemetry / shutdown_telemetry
        # 不报错即验证通过
        assert lifespan is not None


# ============================================================
# 清理环境变量
# ============================================================
@pytest.fixture(autouse=True)
def _clean_env():
    """每个测试后清理 OTel 环境变量，避免跨测试污染。"""
    yield
    for k in (
        "IF_OTEL_ENABLED",
        "IF_OTEL_EXPORTER_OTLP_ENDPOINT",
        "IF_OTEL_SERVICE_NAME",
        "IF_OTEL_CONSOLE_EXPORTER",
    ):
        os.environ.pop(k, None)
    from api.telemetry import _otel_enabled

    if _otel_enabled:
        from api.telemetry import shutdown_telemetry

        shutdown_telemetry()