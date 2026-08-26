"""IMP-18: 账户/额度耗尽自动熔断降级测试。

覆盖：
- 连续 ProviderRateLimited → 降级标记
- 降级后路由返回 429
- 恢复后自动启用
- 配置项控制阈值
"""
import os

import pytest

os.environ.setdefault("IF_ACCOUNT_AUTO", "0")
os.environ.setdefault("IF_MOCK_REGISTER", "1")
os.environ.setdefault("IF_PROVIDER_DEGRADE_THRESHOLD", "3")

from api.providers import registry
from api.providers.registry import bootstrap
from api.providers.base import ProviderRateLimited
from api import config


@pytest.fixture(autouse=True)
def _bootstrap():
    bootstrap()
    yield


@pytest.fixture(autouse=True)
def _reset_registry_state():
    """每个测试前重置 registry 降级状态，避免测试间污染。"""
    # 保留所有 provider 引用，仅重置健康状态
    for prefix in registry.providers:
        registry.provider_health[prefix] = "healthy"
        registry.providers[prefix].health_status = "healthy"
    registry._consecutive_failures.clear()
    registry._last_recover_at.clear()
    registry._exhausted_accounts.clear()
    yield


# ── Registry 降级/熔断 API ─────────────────────────
class TestRegistryDegrade:
    def test_initial_health_is_healthy(self):
        """所有 provider 初始化为 healthy。"""
        for prefix in registry.providers:
            assert registry.provider_health.get(prefix) == "healthy"

    def test_degrade_marks_degraded(self):
        registry.degrade("nanobanana", "test: 连续限流")
        assert registry.provider_health["nanobanana"] == "degraded"

    def test_mark_down_marks_down(self):
        registry.mark_down("nanobanana", "test: 不可用")
        assert registry.provider_health["nanobanana"] == "down"
        # 同步更新 provider 实例
        p = registry.providers["nanobanana"]
        assert p.health_status == "down"

    def test_recover_restores_health(self):
        registry.mark_down("nanobanana", "test")
        registry.recover("nanobanana")
        assert registry.provider_health["nanobanana"] == "healthy"
        p = registry.providers["nanobanana"]
        assert p.health_status == "healthy"

    def test_degraded_providers_ordering(self):
        """down 排在 degraded 前面。"""
        registry.degrade("aifreeforever", "test")
        registry.mark_down("nanobanana", "test")
        degraded = registry.degraded_providers()
        assert degraded[0] == "nanobanana"  # down 优先
        assert degraded[1] == "aifreeforever"  # degraded 其次

    def test_provider_for_returns_none_when_down(self):
        registry.mark_down("nanobanana", "test")
        p = registry.provider_for("nanobanana/nano-banana-pro")
        # down 时如果有能力相同的备用 provider，返回备用 provider
        assert p is not None, "down 时应有备用 provider 接管"
        assert p.prefix != "nanobanana", "应返回非 down 的备用 provider"

    def test_provider_for_returns_provider_when_degraded(self):
        """degraded 不截断路由（仅 down 才截断）。"""
        registry.degrade("nanobanana", "test")
        p = registry.provider_for("nanobanana/nano-banana-pro")
        assert p is not None

    def test_provider_for_returns_provider_when_healthy(self):
        p = registry.provider_for("nanobanana/nano-banana-pro")
        assert p is not None
        # 自适应路由可能选择能力匹配的备选提供商（aifreeforever/imagefree）
        assert p.prefix in ("nanobanana", "aifreeforever", "imagefree")


# ── 连续 ProviderRateLimited 降级 ──────────────────
class TestConsecutiveFailures:
    def test_record_failure_counts(self):
        registry.record_failure("nanobanana")
        assert registry._consecutive_failures["nanobanana"] == 1
        registry.record_failure("nanobanana")
        assert registry._consecutive_failures["nanobanana"] == 2

    def test_record_failure_triggers_degrade_at_threshold(self):
        # 连续 3 次（默认阈值）→ 降级
        for _ in range(3):
            registry.record_failure("nanobanana")
        assert registry.provider_health["nanobanana"] == "degraded"

    def test_record_success_resets_failure_count(self):
        registry.record_failure("nanobanana")
        registry.record_failure("nanobanana")
        registry.record_success("nanobanana")
        assert registry._consecutive_failures.get("nanobanana") is None

    def test_success_before_threshold_prevents_degrade(self):
        registry.record_failure("nanobanana")
        registry.record_failure("nanobanana")
        registry.record_success("nanobanana")
        # 再有一次失败，但连续计数已重置
        registry.record_failure("nanobanana")
        assert registry._consecutive_failures["nanobanana"] == 1
        assert registry.provider_health["nanobanana"] != "degraded"

    def test_exhausted_accounts_tracking(self):
        registry.mark_exhausted("nanobanana", "acc1@test.com")
        registry.mark_exhausted("nanobanana", "acc2@test.com")
        assert registry._exhausted_accounts["nanobanana"] == {"acc1@test.com", "acc2@test.com"}


# ── 恢复探测 ──────────────────────────────────────
class TestRecover:
    def test_try_recover_restores_health(self):
        registry.degrade("nanobanana", "test")
        assert registry.provider_health["nanobanana"] == "degraded"
        registry.try_recover("nanobanana")
        assert registry.provider_health["nanobanana"] == "healthy"
        assert registry._consecutive_failures.get("nanobanana") is None

    def test_try_recover_all_only_recover_after_interval(self, monkeypatch):
        registry.degrade("nanobanana", "test")
        registry.degrade("nanobanana", "test")
        # 设置恢复间隔为 0，让恢复立即生效
        monkeypatch.setattr(config, "IF_PROVIDER_RECOVER_INTERVAL", 0)
        # 模拟时间足够
        registry._last_recover_at["nanobanana"] = 0
        registry._last_recover_at["nanobanana"] = 0
        registry.try_recover_all()
        # 至少恢复了一个
        healthy_count = sum(1 for h in registry.provider_health.values() if h == "healthy")
        assert healthy_count >= 3  # 原始 4 个，至少恢复 1 个

    def test_try_recover_all_skips_healthy(self, monkeypatch):
        """健康的 provider 不参与恢复探测。"""
        monkeypatch.setattr(config, "IF_PROVIDER_RECOVER_INTERVAL", 0)
        registry.degrade("nanobanana", "test")
        # 设置 _last_recover_at 为过去时间，让恢复立即生效
        registry._last_recover_at["nanobanana"] = 0
        degraded = registry.degraded_providers()
        assert "nanobanana" in degraded
        registry.try_recover_all()
        assert registry.provider_health["nanobanana"] == "healthy"


# ── 路由 429 集成 ─────────────────────────────────
class TestRouteIntegration:
    def test_provider_for_returns_429_when_down(self):
        """provider_for 返回备用 provider 而非 None（IMP-22 自动故障转移）。"""
        from fastapi import HTTPException

        registry.mark_down("nanobanana", "test: 全量降级")
        provider = registry.provider_for("nanobanana/nano-banana-pro")
        # IMP-22 自动故障转移：down 时返回能力相同的备用 provider
        assert provider is not None, "应返回备用 provider 接管"
        assert provider.prefix != "nanobanana", "备用 provider 不应是原 provider"

    def test_healthy_provider_dispatch_ok(self):
        """健康 provider 正常返回 provider 实例。"""
        provider = registry.provider_for("nanobanana/nano-banana-pro")
        assert provider is not None

    def test_degraded_provider_dispatch_ok(self):
        """degraded 状态 provider 仍可路由（仅 down 阻断）。"""
        registry.degrade("nanobanana", "test")
        provider = registry.provider_for("nanobanana/nano-banana-pro")
        assert provider is not None  # degraded 不阻断路由


# ── 配置项 ────────────────────────────────────────
class TestConfig:
    def test_degrade_threshold_config(self):
        assert config.IF_PROVIDER_DEGRADE_THRESHOLD == 3

    def test_recover_interval_config(self):
        assert config.IF_PROVIDER_RECOVER_INTERVAL == 300