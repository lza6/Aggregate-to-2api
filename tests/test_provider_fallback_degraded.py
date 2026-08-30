"""P0-2 方案 A：provider_for 对 degraded 首选做「跨商降级」测试。

覆盖（registry 用轻量 stub Provider，不依赖真实 bootstrap/网络）：
- degraded 且有能力匹配的健康备用 → 降级到备用，reason=degraded_fallback
- degraded 但无能力匹配备用（唯一匹配已 down）→ 直连首选保底，reason=direct
- healthy → 精确路由，reason=direct，不跨商
- down → 现有静态回退不回归
"""
from __future__ import annotations

import pytest

from api.providers.base import ModelSpec, Provider, GenerationResult
from api.providers.registry import Registry


class _StubProvider(Provider):
    """极简 Provider：prefix+models，generate 仅返回占位（本测试不真调生成）。"""

    def __init__(self, prefix: str, models: dict[str, ModelSpec]) -> None:
        super().__init__()
        self.prefix = prefix
        self.display_name = prefix
        self.models = models

    async def generate(self, model: str, prompt: str, aspect_ratio: str,
                       images: list[bytes] | None = None, resolution: str = "1K",
                       download: bool = False, **kw) -> GenerationResult:
        return GenerationResult(status="error", error="stub")


def _spec(provider: str, upstream: str, *caps: str) -> ModelSpec:
    mid = f"{provider}/{upstream}"
    return ModelSpec(id=mid, provider=provider, upstream_model=upstream,
                     capabilities=tuple(caps))


@pytest.fixture
def reg() -> Registry:
    r = Registry()
    r.register(_StubProvider("alpha", {
        "alpha/img": _spec("alpha", "img", "txt2img"),
    }))
    r.register(_StubProvider("beta", {
        "beta/img": _spec("beta", "img", "txt2img"),
    }))
    r.register(_StubProvider("gamma", {
        "gamma/vid": _spec("gamma", "vid", "txt2vid"),
    }))
    # 阻止 provider_for 触发真实 bootstrap（避免污染我们的 stub providers）
    r._booted = True
    # adaptive_router 是模块级全局单例，跨测试重置避免 inflight/records 残留
    r.adaptive_router.reset()
    return r


def _last_record(reg: Registry) -> dict:
    return reg.get_routing_records(limit=1)[0]


# ── degraded → 能力匹配的健康备用降级 ────────────────
class TestDegradedFallback:
    def test_degraded_falls_back_to_capability_alt(self, reg):
        """alpha degraded + beta healthy（同一能力 txt2img）→ 降级到 beta。"""
        reg.degrade("alpha", "连续限流")
        p = reg.provider_for("alpha/img")
        assert p is not None and p.prefix == "beta", "应降级到能力匹配的健康备用"
        rec = _last_record(reg)
        assert rec["reason"] == "degraded_fallback"
        assert rec["selected_provider"] == "beta"
        assert rec["requested_provider"] == "alpha"

    def test_degraded_no_capability_alt_direct(self, reg):
        """alpha degraded，唯一能力匹配的 beta 已 down → 直连首选保底。"""
        reg.degrade("alpha", "连续限流")
        reg.mark_down("beta", "不可用")
        p = reg.provider_for("alpha/img")
        assert p is not None and p.prefix == "alpha", "无能力匹配备用时应直连首选"
        rec = _last_record(reg)
        assert rec["reason"] == "direct"
        assert rec["selected_provider"] == "alpha"
        assert rec["requested_provider"] == "alpha"

    def test_degraded_skips_capability_mismatch(self, reg):
        """degraded 时 gamma（txt2vid）能力不匹配 → 不降级到错误能力。"""
        reg.degrade("alpha", "连续限流")
        p = reg.provider_for("alpha/img")
        assert p is not None and p.prefix != "gamma", "降级目标必须能力匹配"
        assert p.prefix == "beta"


# ── healthy 不跨商（现有行为不回归）───────────────────
class TestHealthyPreservesDirect:
    def test_healthy_returns_requested(self, reg):
        p = reg.provider_for("alpha/img")
        assert p is not None and p.prefix == "alpha", "healthy 应精确路由首选"
        rec = _last_record(reg)
        assert rec["reason"] == "direct"
        assert rec["selected_provider"] == "alpha"
        assert rec["requested_provider"] == "alpha"

    def test_healthy_does_not_touch_alt(self, reg):
        """healthy 时不应为其它 provider 记 inflight（不跨商拉流量）。"""
        reg.provider_for("alpha/img")
        snap = reg.adaptive_router.node_snapshot()
        # alpha 应有 inflight 记录；beta/gamma 不应被 healthy 精确路由触碰
        assert snap.get("beta", {}).get("in_flight_requests", 0) == 0
        assert "gamma" not in snap or snap["gamma"].get("in_flight_requests", 0) == 0


# ── down 静态回退不回归 ─────────────────────────────
class TestDownFallbackUnchanged:
    def test_down_falls_back_to_alt(self, reg):
        """alpha down + beta healthy → 静态回退到 beta（既有逻辑）。"""
        reg.mark_down("alpha", "不可用")
        p = reg.provider_for("alpha/img")
        assert p is not None and p.prefix == "beta", "down 应静态回退到能力匹配备用"

    def test_down_prefer_false_returns_down(self, reg):
        reg.mark_down("alpha", "不可用")
        p = reg.provider_for("alpha/img", prefer_healthy=False)
        assert p is not None and p.prefix == "alpha", "prefer_healthy=False 时应直连"


# ── record_fallback 本身 ─────────────────────────────
class TestRecordFallback:
    def test_record_fallback_shape(self, reg):
        reg.adaptive_router.record_fallback("beta", "alpha/img", "alpha")
        rec = _last_record(reg)
        assert rec["reason"] == "degraded_fallback"
        assert rec["selected_provider"] == "beta"
        assert rec["requested_provider"] == "alpha"
        assert rec["model"] == "alpha/img"
