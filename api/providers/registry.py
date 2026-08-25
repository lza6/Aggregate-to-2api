"""模型注册表：统一收集各提供商 ModelSpec，暴露 /v1/models 与路由查找。

命名契约：外部模型 id = "<provider前缀>/<上游真实模型名>"，让 API/前端用户一目了然
上游来源。例：minimaxh3/nano-banana-pro、aifreeforever/gpt-image-2、nanobanana/nano-banana-pro。

路由：自 v3.2 起 provider_for() 结合自适应路由引擎（MAB-EWMA）在候选内实时打分，
不再"只看健康不看实时质量"。降级/熔断仍旧优先。
"""
from __future__ import annotations

import logging

from .base import ModelSpec, Provider
from . import imagefree
from . import minimaxh3
from . import aifreeforever
from . import nanobanana

log = logging.getLogger("registry")


class Registry:
    def __init__(self) -> None:
        self.providers: dict[str, Provider] = {}
        self._models: dict[str, ModelSpec] = {}
        self._booted = False
        # IMP-18: provider 降级/熔断状态（provider前缀 → healthy/degraded/down）
        self.provider_health: dict[str, str] = {}
        # IMP-18: 连续 ProviderRateLimited 计数
        self._consecutive_failures: dict[str, int] = {}
        # IMP-18: 最近恢复探测时间
        self._last_recover_at: dict[str, float] = {}
        # IMP-18: 已耗尽的账号集合（provider → set of account identifiers）
        self._exhausted_accounts: dict[str, set[str]] = {}
        # v3.2: MAB-EWMA 自适应路由引擎
        from ..adaptive_router import adaptive_router
        self.adaptive_router = adaptive_router

    def _ensure_booted(self) -> None:
        if not self._booted:
            bootstrap()
            self._booted = True

    def register(self, provider: Provider) -> None:
        self.providers[provider.prefix] = provider
        for mid, spec in provider.models.items():
            self._models[mid] = spec
        # IMP-18: 设置 provider 对 registry 的引用
        provider._registry_ref = self
        # 初始化健康状态
        self.provider_health[provider.prefix] = "healthy"
        log.info("注册提供商 %s（%d 模型）", provider.prefix, len(provider.models))

    def model(self, model_id: str) -> ModelSpec | None:
        self._ensure_booted()
        return self._models.get(model_id)

    def get_routing_records(self, limit: int = 50) -> list[dict]:
        """返回最近 limit 条自适应路由决策记录（供 /v1/routing/records 端点）。"""
        return self.adaptive_router.records(limit=limit)

    def provider_for(self, model_id: str, prefer_healthy: bool = True) -> Provider | None:
        """返回 model_id 对应的提供商。

        路由逻辑（v3.2）：
        1. 首选 provider down → find_alternative（静态能力匹配回退）
        2. 首选 provider healthy/degraded → 在候选（首+备）中用自适应路由打分发流量
        3. 全都不行 → 回退首选（最坏也只是慢，不 429）
        路由决策会写入 adaptive_router 的路由记录，供 /v1/routing/records 展示。
        """
        self._ensure_booted()
        spec = self._models.get(model_id)
        if not spec:
            return None
        provider = self.providers.get(spec.provider)
        if provider is None:
            return None
        # IMP-18: 检查降级/熔断状态（同时检查 registry 级和 provider 实例级的健康状态）
        health = self.provider_health.get(spec.provider, "healthy")
        if provider and provider.health_status == "down":
            health = "down"

        if health == "down":
            # provider 为 down → 尝试找备用（静态回退，不参与自适应打分）
            if not prefer_healthy:
                return provider
            alt_provider, alt_model_id = self.find_alternative(model_id)
            if alt_provider:
                self.adaptive_router.record_inflight(alt_provider.prefix)
            return alt_provider or provider

        # 首选 healthy/degraded → 组装候选（首选 + 各能力匹配的备用）交给自适应路由
        candidates = [spec.provider]
        # 仅当目标提供商不是明确指定专有前缀（如 imagefree/* 专属）或显式需要降级时才交叉打分
        if spec.provider != "imagefree":
            for prefix, p in self.providers.items():
                if prefix == spec.provider:
                    continue
                if p.health_status == "down":
                    continue  # 熔断/不可用不参与
                for mid, ms in p.models.items():
                    if set(spec.capabilities) & set(ms.capabilities):
                        candidates.append(prefix)
                        break
        # 去重保序，交给 MAB-EWMA 打分
        seen: set[str] = set()
        uniq = [c for c in candidates if not (c in seen or seen.add(c))]

        selected = self.adaptive_router.select_best(
            uniq,
            model=model_id,
            requested_provider=spec.provider,
        )
        chosen = self.providers.get(selected) or provider
        return chosen

    def find_alternative(self, model_id: str) -> tuple[Provider | None, str | None]:
        """查找 model_id 的备用提供商。

        返回 (备用 Provider, 备用模型 ID)。如果找不到能力匹配的健康 provider 则返回 (None, None)。
        """
        spec = self._models.get(model_id)
        if not spec:
            return None, None
        # 确定当前模型需要的能力
        needed_capabilities = set(spec.capabilities)
        for prefix, p in self.providers.items():
            if p.health_status == "down":
                continue
            if prefix == spec.provider:
                continue  # 跳过自身
            # 检查该 provider 是否有能覆盖所需能力的模型
            for mid, ms in p.models.items():
                # 检查是否有至少一个能力匹配（交集非空）
                # 降级时优先找能力重叠最多的，但至少有一个匹配
                common = needed_capabilities & set(ms.capabilities)
                if common:
                    return p, mid
        return None, None

    # ── Provider 降级/熔断（IMP-18）────────────────────
    def degrade(self, provider: str, reason: str) -> None:
        """标记 provider 为 degraded（连续限流/额度耗尽）。"""
        old = self.provider_health.get(provider, "healthy")
        self.provider_health[provider] = "degraded"
        self._last_recover_at[provider] = __import__("time").time()
        if old != "degraded":
            log.warning("提供商 %s 降级为 degraded: %s", provider, reason)

    def mark_down(self, provider: str, reason: str) -> None:
        """标记 provider 为 down（不可用）。"""
        old = self.provider_health.get(provider, "healthy")
        self.provider_health[provider] = "down"
        # 同步更新 provider 实例的 health_status
        p = self.providers.get(provider)
        if p:
            p.health_status = "down"
        self._last_recover_at[provider] = __import__("time").time()
        if old != "down":
            log.warning("提供商 %s 标记为 down: %s", provider, reason)

    def degraded_providers(self) -> list[str]:
        """返回降级或不可用的提供商前缀列表（按降级程度排序：down > degraded）。"""
        down = [p for p, h in self.provider_health.items() if h == "down"]
        degraded = [p for p, h in self.provider_health.items() if h == "degraded"]
        return down + degraded

    def recover(self, provider: str) -> None:
        """恢复 provider 为健康状态。"""
        old = self.provider_health.get(provider, "healthy")
        self.provider_health[provider] = "healthy"
        # 同步更新 provider 实例的 health_status
        p = self.providers.get(provider)
        if p:
            p.health_status = "healthy"
        if old != "healthy":
            log.info("提供商 %s 恢复为 healthy", provider)

    # ── 连续失败追踪（IMP-18）────────────────────────
    def record_failure(self, provider: str) -> None:
        """记录连续 ProviderRateLimited 失败，达到配置阈值自动降级。"""
        from .. import config
        count = self._consecutive_failures.get(provider, 0) + 1
        self._consecutive_failures[provider] = count
        if count >= config.IF_PROVIDER_DEGRADE_THRESHOLD:
            self.degrade(provider, f"连续 {count} 次 ProviderRateLimited")

    def record_success(self, provider: str) -> None:
        """重置连续失败计数。如果 provider 处于 degraded 状态，自动恢复为 healthy。"""
        self._consecutive_failures.pop(provider, None)
        if self.provider_health.get(provider) == "degraded":
            self.recover(provider)

    def mark_exhausted(self, provider: str, account_id: str) -> None:
        """标记该 provider 的指定账号已耗尽。"""
        self._exhausted_accounts.setdefault(provider, set()).add(account_id)

    def try_recover(self, provider: str) -> None:
        """尝试恢复一个降级 provider。"""
        old = self.provider_health.get(provider, "healthy")
        if old != "healthy":
            self.recover(provider)
            self._consecutive_failures.pop(provider, None)

    def try_recover_all(self) -> None:
        """遍历所有降级/不可用 provider，尝试恢复一个。"""
        from .. import config
        now = __import__("time").time()
        for provider in self.degraded_providers():
            last = self._last_recover_at.get(provider, 0.0)
            if now - last >= config.IF_PROVIDER_RECOVER_INTERVAL:
                self.try_recover(provider)
                self._last_recover_at[provider] = now
                break  # 每次只恢复一个，避免全部同时恢复造成冲击

    def all_models(self) -> list[ModelSpec]:
        self._ensure_booted()
        return list(self._models.values())

    def grouped(self) -> dict[str, list[dict]]:
        """按提供商分组，供 /v1/models 与前端展示。"""
        self._ensure_booted()
        out: dict[str, list[dict]] = {}
        for m in self._models.values():
            out.setdefault(m.provider, []).append({
                "id": m.id,
                "name": m.display_name or m.upstream_model,
                "upstream_model": m.upstream_model,
                "capabilities": list(m.capabilities),
                "aspect_ratios": list(m.aspect_ratios),
                "resolutions": list(m.resolutions),
                "credits": m.credits,
                "account_required": m.account_required,
                "description": m.description,
            })
        return out

    def provider_summary(self) -> dict[str, dict]:
        """每个提供商的看板摘要（状态/能力/模型数/额度），前端与 healthz 用。"""
        self._ensure_booted()
        out = {}
        for prefix, p in self.providers.items():
            out[prefix] = {
                "display_name": p.display_name,
                "base_url": p.base_url,
                "capabilities": [c for c in ("txt2img", "img2img", "txt2vid", "img2vid") if p.supports(c)],
                "model_count": sum(1 for m in self._models.values() if m.provider == prefix),
                "needs_account": p.needs_account(),
                "needs_proxy_per_request": p.needs_proxy_per_request(),
                "health_status": p.health_status,  # IMP-22: 暴露健康状态
            }
        return out

    # ── 健康探测（IMP-22）──────────────────────────
    def healthy_providers(self) -> list[str]:
        """返回健康状态为 healthy 或 unknown 的 provider 前缀列表。"""
        return [
            prefix for prefix, p in self.providers.items()
            if p.health_status in ("healthy", "unknown")
        ]

    async def health_check_all(self) -> None:
        """遍历所有 provider 执行健康检查。"""
        for prefix, p in self.providers.items():
            try:
                status = await p.health_check()
                p.health_status = status
                p.last_health_check = __import__("time").time()
                if status == "down":
                    log.warning("提供商 %s 健康检查失败，标记为 down", prefix)
                elif status == "degraded":
                    log.warning("提供商 %s 健康检查 degraded", prefix)
            except Exception as e:
                p.health_status = "down"
                p.last_health_check = __import__("time").time()
                log.warning("提供商 %s 健康检查异常，标记为 down: %s", prefix, e)


# 模块级单例（main 启动时调用 bootstrap 加载各提供商）
registry = Registry()


def bootstrap() -> None:
    """创建并注册全部提供商实例（幂等）。

    架构优化：已移除用完即丢且不可签到的冗余提供商（minimaxh3），
    将所有算力与号池集中在支持每日自动签到续额的长效提供商（nanobanana）
    以及主力提供商（imagefree, aifreeforever）。
    """
    if registry.providers:
        return
    registry.register(imagefree.ImagefreeProvider())
    registry.register(aifreeforever.AifreeforeverProvider())
    registry.register(nanobanana.NanobananaProvider())


async def startup_all() -> None:
    bootstrap()
    for p in registry.providers.values():
        try:
            await p.startup()
        except Exception as e:
            log.warning("提供商 %s 启动失败（可忽略，降级）: %s", p.prefix, e)


async def shutdown_all() -> None:
    for p in registry.providers.values():
        try:
            await p.shutdown()
        except Exception as e:
            log.warning("提供商 %s 停止失败: %s", p.prefix, e)
