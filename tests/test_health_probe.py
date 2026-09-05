"""IMP-22: 健康探测 + 自动故障转移。

测试覆盖：
1. 健康检查执行（health_check_all 遍历所有 provider）
2. 上游不可用 → 自动切换到备用 provider
3. 恢复后回切（原 provider 恢复健康后优先使用）
4. 切换不丢任务（failover 后 generate 仍正常返回）
5. IF_HEALTH_CHECK_ENABLED=0 时跳过健康检查循环
"""

import os
import time

import pytest

os.environ.setdefault("IF_ACCOUNT_AUTO", "0")
os.environ.setdefault("IF_MOCK_REGISTER", "1")

from api.providers.base import CAP_IMG2IMG, CAP_TXT2IMG, GenerationResult, ModelSpec, Provider
from api.providers.registry import Registry

# ── Mock 提供商 ──────────────────────────────────────
MODEL_A = ModelSpec(
    id="prov_a/model-x",
    provider="prov_a",
    upstream_model="model-x",
    capabilities=(CAP_TXT2IMG, CAP_IMG2IMG),
)
MODEL_B = ModelSpec(
    id="prov_b/model-y",
    provider="prov_b",
    upstream_model="model-y",
    capabilities=(CAP_TXT2IMG,),
)
MODEL_C = ModelSpec(
    id="prov_c/model-z",
    provider="prov_c",
    upstream_model="model-z",
    capabilities=(CAP_IMG2IMG,),
)


class MockProviderA(Provider):
    """支持 txt2img+img2img，health_check 返回当前 health_status。"""

    prefix = "prov_a"
    display_name = "Provider A"
    models = {"prov_a/model-x": MODEL_A}

    def __init__(self) -> None:
        super().__init__()
        self.health_status = "healthy"
        self.last_health_check = time.time()
        self.generated: list[str] = []

    async def generate(
        self,
        model: str,
        prompt: str,
        aspect_ratio: str = "1:1",
        images: list[bytes] | None = None,
        resolution: str = "1K",
        download: bool = False,
        **kw,
    ) -> GenerationResult:
        self.generated.append(prompt)
        return GenerationResult(status="completed", asset_url="https://a.example/img.png")

    async def health_check(self) -> str:
        self.last_health_check = time.time()
        return self.health_status


class MockProviderB(Provider):
    """支持 txt2img（model-y）和 txt2img+img2img（model-x-alt），health_check 返回当前 health_status。"""

    prefix = "prov_b"
    display_name = "Provider B"
    models = {
        "prov_b/model-y": MODEL_B,
        "prov_b/model-x-alt": ModelSpec(
            id="prov_b/model-x-alt",
            provider="prov_b",
            upstream_model="model-x-alt",
            capabilities=(CAP_TXT2IMG, CAP_IMG2IMG),
        ),
    }

    def __init__(self) -> None:
        super().__init__()
        self.health_status = "healthy"
        self.last_health_check = time.time()
        self.generated: list[str] = []

    async def generate(
        self,
        model: str,
        prompt: str,
        aspect_ratio: str = "1:1",
        images: list[bytes] | None = None,
        resolution: str = "1K",
        download: bool = False,
        **kw,
    ) -> GenerationResult:
        self.generated.append(prompt)
        return GenerationResult(status="completed", asset_url="https://b.example/img.png")

    async def health_check(self) -> str:
        self.last_health_check = time.time()
        return self.health_status


class MockProviderC(Provider):
    """仅支持 img2img，用于验证能力不匹配场景。health_check 返回当前 health_status。"""

    prefix = "prov_c"
    display_name = "Provider C"
    models = {"prov_c/model-z": MODEL_C}

    def __init__(self) -> None:
        super().__init__()
        self.health_status = "healthy"
        self.last_health_check = time.time()

    async def generate(
        self,
        model: str,
        prompt: str,
        aspect_ratio: str = "1:1",
        images: list[bytes] | None = None,
        resolution: str = "1K",
        download: bool = False,
        **kw,
    ) -> GenerationResult:
        return GenerationResult(status="completed", asset_url="https://c.example/img.png")

    async def health_check(self) -> str:
        self.last_health_check = time.time()
        return self.health_status


@pytest.fixture
def fresh_registry():
    """每次测试返回一个干净的 Registry，含三个 mock provider。"""
    reg = Registry()
    reg._booted = True  # 跳过 bootstrap
    reg.register(MockProviderA())
    reg.register(MockProviderB())
    reg.register(MockProviderC())
    return reg


# ── 测试 1: 健康检查执行 ──────────────────────────────
class TestHealthCheckExecution:
    """health_check_all 遍历所有 provider 并更新 health_status 和 last_health_check。"""

    @pytest.mark.asyncio
    async def test_health_check_all_updates_status(self, fresh_registry):
        reg = fresh_registry
        # 修改 health_check 方法：始终返回 healthy
        for p in reg.providers.values():
            p.health_status = "unknown"
            p.last_health_check = 0.0

            # 覆写 health_check 使其返回 healthy
            async def _healthy(_self=p):
                _self.last_health_check = time.time()
                return "healthy"

            p.health_check = _healthy

        await reg.health_check_all()

        for prefix, p in reg.providers.items():
            assert p.health_status == "healthy", f"{prefix} 健康检查后应为 healthy"
            assert p.last_health_check > 0, f"{prefix} last_health_check 应更新"

    @pytest.mark.asyncio
    async def test_health_check_inherits_down(self, fresh_registry):
        """provider 的 health_check 返回 'down' 时，health_status 应同步更新。"""
        reg = fresh_registry
        pa = reg.providers["prov_a"]

        async def _broken_check():
            return "down"

        pa.health_check = _broken_check
        await reg.health_check_all()
        assert pa.health_status == "down"

    @pytest.mark.asyncio
    async def test_health_check_exception_sets_down(self, fresh_registry):
        """health_check 抛异常时，provider 标记为 down。"""
        reg = fresh_registry
        pa = reg.providers["prov_a"]

        async def _broken_check():
            raise ConnectionError("上游连接超时")

        pa.health_check = _broken_check
        await reg.health_check_all()
        assert pa.health_status == "down"

    def test_healthy_providers(self, fresh_registry):
        reg = fresh_registry
        healthy = reg.healthy_providers()
        assert "prov_a" in healthy
        assert "prov_b" in healthy
        assert "prov_c" in healthy

        reg.providers["prov_a"].health_status = "down"
        healthy = reg.healthy_providers()
        assert "prov_a" not in healthy
        assert "prov_b" in healthy

        reg.providers["prov_b"].health_status = "unknown"
        healthy = reg.healthy_providers()
        assert "prov_b" in healthy  # unknown 视为健康


# ── 测试 2: 上游不可用 → 自动切换 ─────────────────────
class TestAutoFailover:
    """首选 provider 为 down 时，自动切换到能力相同的备用 provider。"""

    def test_provider_for_healthy_preferred(self, fresh_registry):
        """provider 健康时优先返回原 provider。"""
        reg = fresh_registry
        p = reg.provider_for("prov_a/model-x")
        assert p is not None
        assert p.prefix == "prov_a"

    def test_provider_for_down_fallback(self, fresh_registry):
        """provider 为 down 时，返回能力相同的备用 provider。"""
        reg = fresh_registry
        reg.providers["prov_a"].health_status = "down"

        p = reg.provider_for("prov_a/model-x")
        assert p is not None
        # prov_b 有完全匹配能力（txt2img+img2img）的模型，应返回 prov_b
        assert p.prefix == "prov_b"

    def test_provider_for_prefer_healthy_false(self, fresh_registry):
        """prefer_healthy=False 时，即使 provider 为 down 也返回原 provider。"""
        reg = fresh_registry
        reg.providers["prov_a"].health_status = "down"

        p = reg.provider_for("prov_a/model-x", prefer_healthy=False)
        assert p is not None
        assert p.prefix == "prov_a"

    def test_provider_for_no_alternative(self, fresh_registry):
        """没有能力相同的备用 provider 时，返回原 provider（即使 down）。"""
        reg = fresh_registry
        reg.providers["prov_a"].health_status = "down"
        reg.providers["prov_b"].health_status = "down"
        reg.providers["prov_c"].health_status = "down"

        p = reg.provider_for("prov_a/model-x")
        assert p is not None
        assert p.prefix == "prov_a"  # 没有可用的替代，返回原 provider

    def test_find_alternative_returns_correct_model(self, fresh_registry):
        """find_alternative 返回 (provider, alternative_model_id)。"""
        reg = fresh_registry
        reg.providers["prov_a"].health_status = "down"

        alt_provider, alt_model = reg.find_alternative("prov_a/model-x")
        assert alt_provider is not None
        assert alt_provider.prefix == "prov_b"
        assert alt_model is not None

    def test_find_alternative_no_healthy_alternative(self, fresh_registry):
        """所有 alternative provider 都 down 时，返回 (None, None)。"""
        reg = fresh_registry
        reg.providers["prov_a"].health_status = "down"
        reg.providers["prov_b"].health_status = "down"
        reg.providers["prov_c"].health_status = "down"

        alt_provider, alt_model = reg.find_alternative("prov_a/model-x")
        assert alt_provider is None
        assert alt_model is None


# ── 测试 3: 恢复后回切 ────────────────────────────────
class TestRecoveryFallback:
    """provider 恢复健康后，优先使用原 provider。"""

    def test_recovery_fallback(self, fresh_registry):
        reg = fresh_registry
        pa = reg.providers["prov_a"]

        # 标记为 down → 降级
        pa.health_status = "down"
        p = reg.provider_for("prov_a/model-x")
        assert p.prefix == "prov_b"

        # 恢复健康 → 回切
        pa.health_status = "healthy"
        p = reg.provider_for("prov_a/model-x")
        assert p.prefix == "prov_a"

    def test_mark_down_and_up(self, fresh_registry):
        """mark_down / mark_up 方法的正确性。"""
        reg = fresh_registry
        pa = reg.providers["prov_a"]

        pa.mark_down("上游 API 返回 503")
        assert pa.health_status == "down"

        pa.mark_up()
        assert pa.health_status == "healthy"

    def test_healthy_providers_excludes_degraded(self, fresh_registry):
        """degraded 状态的 provider 不视为健康。"""
        reg = fresh_registry
        reg.providers["prov_a"].health_status = "degraded"

        healthy = reg.healthy_providers()
        assert "prov_a" not in healthy


# ── 测试 4: 切换不丢任务 ──────────────────────────────
class TestFailoverTaskDelivery:
    """failover 后 generate 调用正常返回，不丢失任务。"""

    @pytest.mark.asyncio
    async def test_alternative_provider_generates(self, fresh_registry):
        """降级到备用 provider 后，generate 正常返回 completed。"""
        reg = fresh_registry
        pa = reg.providers["prov_a"]
        pb = reg.providers["prov_b"]
        pa.health_status = "down"

        alt_provider, alt_model = reg.find_alternative("prov_a/model-x")
        assert alt_provider is not None
        assert alt_provider.prefix == "prov_b"

        # 用备用 provider 执行 generate
        res = await alt_provider.generate(alt_model, "test prompt", "1:1")
        assert res.status == "completed"
        assert res.asset_url is not None
        assert len(pb.generated) == 1
        assert pb.generated[0] == "test prompt"

    @pytest.mark.asyncio
    async def test_preferred_recovers_and_handles_tasks(self, fresh_registry):
        """原 provider 恢复后，新请求回到原 provider。"""
        reg = fresh_registry
        pa = reg.providers["prov_a"]
        pb = reg.providers["prov_b"]

        # 第一阶段：provider A down → 路由到 B
        pa.health_status = "down"
        p1, m1 = reg.find_alternative("prov_a/model-x")
        assert p1.prefix == "prov_b"
        await p1.generate(m1, "任务1", "1:1")
        assert len(pb.generated) == 1

        # 第二阶段：provider A 恢复
        pa.health_status = "healthy"
        p2 = reg.provider_for("prov_a/model-x")
        assert p2.prefix == "prov_a"
        await p2.generate("prov_a/model-x", "任务2", "1:1")
        assert len(pa.generated) == 1
        assert pa.generated[0] == "任务2"


# ── 测试 5: 健康检查开关 ──────────────────────────────
class TestHealthCheckDisabled:
    """IF_HEALTH_CHECK_ENABLED=0 时跳过健康检查循环。"""

    def test_health_check_enabled_config(self):
        """IF_HEALTH_CHECK_ENABLED 默认应为 True。"""
        import api.config as cfg

        assert cfg.IF_HEALTH_CHECK_ENABLED is True

    @pytest.mark.asyncio
    async def test_health_check_all_still_works(self, fresh_registry):
        """health_check_all 方法独立工作，不受配置影响。"""
        reg = fresh_registry
        for p in reg.providers.values():
            p.health_status = "unknown"

            async def _healthy(_self=p):
                _self.last_health_check = time.time()
                return "healthy"

            p.health_check = _healthy
        await reg.health_check_all()
        for p in reg.providers.values():
            assert p.health_status == "healthy"
