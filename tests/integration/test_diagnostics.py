"""诊断与慢日志端点集成测试（v3.1.0 T-2/T-3）。

覆盖：/v1/diagnostics 只读零副作用 + 各 section 字段齐全；/v1/slow 阈值与统计。
"""

import pytest


@pytest.mark.integration
class TestDiagnostics:
    """S-6: /v1/diagnostics 只读体检端点。"""

    async def test_diagnostics_sections(self, app_with_mocks):
        r = await app_with_mocks.get("/v1/diagnostics")
        assert r.status_code == 200
        body = r.json()
        # 顶层结构
        assert body["status"] == "ok"
        assert isinstance(body["timestamp"], int)
        # 各 section 存在
        for section in ("db", "queue", "workers", "token_pools", "solver", "slow_log", "disk"):
            assert section in body, f"缺少 {section} 段"
        # db 段字段
        assert "size_mb" in body["db"]
        assert "rows" in body["db"]
        assert "wal_size_mb" in body["db"]
        # queue 段字段
        for f in ("queued", "capacity", "admin", "high", "normal", "processing"):
            assert f in body["queue"]
        # workers 段（summary + detail）
        assert "total" in body["workers"]
        assert "alive" in body["workers"]
        assert isinstance(body["workers"]["detail"], list)
        if body["workers"]["detail"]:
            w0 = body["workers"]["detail"][0]
            for f in ("id", "alive", "stale", "last_active_ago_seconds", "processed"):
                assert f in w0

    async def test_diagnostics_readonly(self, app_with_mocks):
        """只读性：连续调用两次，rows 数不变（无写入副作用）。"""
        r1 = await app_with_mocks.get("/v1/diagnostics")
        rows1 = r1.json()["db"]["rows"]
        r2 = await app_with_mocks.get("/v1/diagnostics")
        rows2 = r2.json()["db"]["rows"]
        assert rows1 == rows2


@pytest.mark.integration
class TestSlowEndpoint:
    """S-3/S-4: /v1/slow 慢请求画像端点。"""

    async def test_slow_endpoint_shape(self, app_with_mocks):
        r = await app_with_mocks.get("/v1/slow")
        assert r.status_code == 200
        body = r.json()
        assert "threshold_ms" in body
        assert "enabled" in body
        assert "stats" in body
        assert "items" in body
        assert "count" in body
        assert body["enabled"] is True
        stats = body["stats"]
        for f in ("count", "avg_total_ms", "max_total_ms"):
            assert f in stats

    async def test_slow_limit_param(self, app_with_mocks):
        r = await app_with_mocks.get("/v1/slow?limit=1")
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 1
