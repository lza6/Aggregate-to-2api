"""api/health.py HealthRegistry 单元测试（P0-2 覆盖率补强）。

覆盖：register/check_all 的全部 check_fn 返回类型分支（async/sync × bool/str/HealthStatus/
异常）、consecutive_failures 累计与清零、degraded_components 排序、overall_status 聚合、
snapshot 结构。
"""

from __future__ import annotations

import pytest

from api.health import HealthRegistry, HealthStatus


def _mk_status(status: str, message: str = "") -> HealthStatus:
    return HealthStatus(component="c", status=status, last_check=0.0, message=message)  # type: ignore[arg-type]


# ── register + check_all：各返回类型分支 ─────────────────────


@pytest.mark.asyncio
async def test_register_initializes_healthy():
    reg = HealthRegistry()
    reg.register("db", lambda: True)
    snap = reg.snapshot()
    assert snap["status"] == "ok"
    assert snap["components"]["db"]["status"] == "healthy"
    assert snap["degraded"] == []


@pytest.mark.asyncio
async def test_check_all_bool_true_false():
    reg = HealthRegistry()
    reg.register("ok_comp", lambda: True)
    reg.register("bad_comp", lambda: False)
    result = await reg.check_all()
    assert result["ok_comp"].status == "healthy"
    assert result["bad_comp"].status == "down"
    assert result["bad_comp"].consecutive_failures == 1
    assert result["bad_comp"].message == "check failed"


@pytest.mark.asyncio
async def test_check_all_str_status_names():
    reg = HealthRegistry()
    reg.register("deg", lambda: "degraded")
    reg.register("ok_word", lambda: "ok")
    reg.register("up_word", lambda: "up")
    reg.register("alive_word", lambda: "alive")
    reg.register("bad_word", lambda: "boom: detail")
    result = await reg.check_all()
    assert result["deg"].status == "degraded"
    assert result["ok_word"].status == "healthy" and result["ok_word"].message == "ok"
    assert result["up_word"].status == "healthy"
    assert result["alive_word"].status == "healthy"
    assert result["bad_word"].status == "down" and result["bad_word"].message == "boom: detail"


@pytest.mark.asyncio
async def test_check_all_healthstatus_passthrough():
    reg = HealthRegistry()
    reg.register("custom", lambda: _mk_status("degraded", "queue backpressure"))
    result = await reg.check_all()
    assert result["custom"].status == "degraded"
    assert result["custom"].message == "queue backpressure"


@pytest.mark.asyncio
async def test_check_all_async_fn():
    async def good():
        return True

    async def bad():
        raise RuntimeError("conn refused")

    reg = HealthRegistry()
    reg.register("a", good)
    reg.register("b", bad)
    result = await reg.check_all()
    assert result["a"].status == "healthy"
    assert result["b"].status == "down" and "conn refused" in result["b"].message


@pytest.mark.asyncio
async def test_check_all_unknown_type_defaults_healthy():
    reg = HealthRegistry()
    reg.register("weird", lambda: 12345)  # 非 bool/str/HealthStatus → 默认 healthy
    result = await reg.check_all()
    assert result["weird"].status == "healthy"


# ── consecutive_failures 累计 / 恢复清零 ─────────────────────


@pytest.mark.asyncio
async def test_consecutive_failures_accumulate_then_reset():
    reg = HealthRegistry()
    state = {"ok": False}
    reg.register("flaky", lambda: state["ok"])
    await reg.check_all()
    await reg.check_all()
    assert reg.snapshot()["components"]["flaky"]["consecutive_failures"] == 2
    state["ok"] = True
    await reg.check_all()
    assert reg.snapshot()["components"]["flaky"]["consecutive_failures"] == 0


# ── degraded_components / overall_status ─────────────────────


@pytest.mark.asyncio
async def test_degraded_components_down_before_degraded():
    reg = HealthRegistry()
    reg.register("d1", lambda: "degraded")
    reg.register("x1", lambda: False)  # down
    reg.register("d2", lambda: "degraded")
    await reg.check_all()
    assert reg.degraded_components() == ["x1", "d1", "d2"]  # down 在前
    assert reg.overall_status() == "down"


@pytest.mark.asyncio
async def test_overall_status_degraded_only():
    reg = HealthRegistry()
    reg.register("d", lambda: "degraded")
    await reg.check_all()
    assert reg.overall_status() == "degraded"


@pytest.mark.asyncio
async def test_overall_status_all_healthy():
    reg = HealthRegistry()
    reg.register("a", lambda: True)
    await reg.check_all()
    assert reg.overall_status() == "ok"


# ── snapshot 结构 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_snapshot_contains_component_details():
    reg = HealthRegistry()
    reg.register("svc", lambda: True)
    await reg.check_all()
    snap = reg.snapshot()
    c = snap["components"]["svc"]
    assert set(c) == {"status", "last_check", "consecutive_failures", "message"}
    assert c["status"] == "healthy"
    assert snap["status"] == "ok"


def test_module_singleton_exists():
    from api import health as h

    assert isinstance(h.health_registry, HealthRegistry)
