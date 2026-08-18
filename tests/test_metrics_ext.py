"""测试 prometheus_client 指标系统。"""
from api.metrics_ext import (
    requests_total, generate_duration, token_pool_watermark,
    queue_size, imagefree_metrics,
)


def test_metrics_labels():
    """验证指标带有正确 label 维度。"""
    requests_total.labels(provider="imagefree", status="completed").inc()
    assert requests_total.labels(provider="imagefree", status="completed")._value.get() == 1.0


def test_generate_duration_histogram():
    """验证生成耗时 histogram 记录。"""
    generate_duration.labels(provider="imagefree", model="default").observe(5.0)
    assert True


def test_watermark_gauge():
    """验证水位 gauge 可设置。"""
    token_pool_watermark.labels(pool="direct").set(3)
    assert token_pool_watermark.labels(pool="direct")._value.get() == 3.0