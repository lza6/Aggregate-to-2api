"""模型注册表：统一收集各提供商 ModelSpec，暴露 /v1/models 与路由查找。

命名契约：外部模型 id = "<provider前缀>/<上游真实模型名>"，让 API/前端用户一目了然
上游来源。例：nanobanana/nano-banana-pro、aifreeforever/gpt-image-2、imagefree/default。

路由：自 v3.2 起 provider_for() 结合自适应路由引擎（MAB-EWMA）在候选内实时打分，
不再"只看健康不看实时质量"。降级/熔断仍旧优先。
"""
from __future__ import annotations

import logging

from .base import ModelSpec, Provider
from . import imagefree
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
        # v4.4: 文本对话提供商注册表（prefix → ChatProvider）+ 模型索引
        self.chat_providers: dict[str, "ChatProvider"] = {}  # type: ignore[name-defined]
        self._chat_models: dict[str, ModelSpec] = {}

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

    def register_chat(self, provider) -> None:
        """注册文本对话 ChatProvider（v4.4）。模型 id 前缀与图像 Provider 同契约。"""
        from .base import ChatProvider  # 延迟导入防循环
        if not isinstance(provider, ChatProvider):
            raise TypeError(f"{type(provider).__name__} 不是 ChatProvider")
        self.chat_providers[provider.prefix] = provider
        for mid, spec in provider.models.items():
            self._chat_models[mid] = spec
        provider._registry_ref = self  # type: ignore[attr-defined]
        log.info("注册聊天提供商 %s（%d 模型）", provider.prefix, len(provider.models))

    def chat_model(self, model_id: str) -> ModelSpec | None:
        """查找聊天模型 spec。未找到时尝试从各 provider 动态目录补查。"""
        self._ensure_booted()
        spec = self._chat_models.get(model_id)
        if spec is not None:
            return spec
        # 动态目录回退：模型 id 可能是刷新后新增的（如 glm-5.3-flash），按前缀委托查询
        prefix = model_id.split("/", 1)[0]
        prov = self.chat_providers.get(prefix)
        if prov is not None:
            spec = prov.models.get(model_id)
            if spec is not None:
                self._chat_models[model_id] = spec
        return spec

    def all_chat_models(self) -> list[ModelSpec]:
        """全部聊天模型（含动态目录）。"""
        self._ensure_booted()
        out: dict[str, ModelSpec] = dict(self._chat_models)
        for prov in self.chat_providers.values():
            out.update(prov.models)
        return list(out.values())

    def model(self, model_id: str) -> ModelSpec | None:
        self._ensure_booted()
        return self._models.get(model_id)

    def get_routing_records(self, limit: int = 50) -> list[dict]:
        """返回最近 limit 条自适应路由决策记录（供 /v1/routing/records 端点）。"""
        return self.adaptive_router.records(limit=limit)

    def provider_for(self, model_id: str, prefer_healthy: bool = True) -> Provider | None:
        """返回 model_id 对应的提供商。

        路由逻辑（直接映射，不做跨提供商自动降级）：
        - 仅当首选 provider 明确 down 时才静态回退到能力匹配的备用（避免请求 429）。
        - healthy/degraded 的提供商**不**参与跨提供商 MAB-EWMA 打分，
          直接返回请求指定的提供商（model_id 前缀即提供商），保证用户指定的
          nanobanana/aifreeforever 等模型真实路由到对应提供商，而非被自动路由偷换。
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

        # 首选 down → 静态回退到能力匹配的备用（仅此场景跨提供商）
        if health == "down":
            if not prefer_healthy:
                return provider
            alt_provider, alt_model_id = self.find_alternative(model_id)
            if alt_provider:
                self.adaptive_router.record_inflight(alt_provider.prefix)
                log.info("提供商 %s down，静态回退到 %s 处理 %s",
                         spec.provider, alt_provider.prefix, model_id)
            return alt_provider or provider

        # healthy/degraded → 直接返回请求指定的提供商（不做自适应交叉路由）
        # 记录一次路由决策（selected = requested，reason=direct）供前端观测
        try:
            self.adaptive_router.record_inflight(spec.provider)
            self.adaptive_router.record_direct(spec.provider, model_id)
        except Exception:
            pass
        return provider

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
        # 同步更新 provider 实例的 health_status
        p = self.providers.get(provider)
        if p:
            p.health_status = "degraded"
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
        """每个提供商的看板摘要（状态/能力/模型数/额度/错误计数/降级标记），前端与 healthz 用。"""
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
                "error_count": self._consecutive_failures.get(prefix, 0),  # P1-E: 连续失败计数
                "degraded": p.health_status == "degraded",  # P1-E: 是否为降级状态
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

    架构优化：已移除用完即丢且不可签到的冗余提供商，
    将所有算力与号池集中在支持每日自动签到续额的长效提供商（nanobanana）
    以及主力提供商（imagefree, aifreeforever）。
    v4.4: 同步注册文本对话 ChatProvider（tryingopen，可通过 IF_TRYINGOPEN_ENABLED 关闭）。
    """
    if registry.providers:
        return
    registry.register(imagefree.ImagefreeProvider())
    registry.register(aifreeforever.AifreeforeverProvider())
    registry.register(nanobanana.NanobananaProvider())
    # v4.4: 文本对话提供商（导入失败/开关关闭时静默跳过，不影响图像主链路）
    import os
    if os.getenv("IF_TRYINGOPEN_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}:
        try:
            from .tryingopen import TryingopenChatProvider
            registry.register_chat(TryingopenChatProvider())
        except Exception as e:
            log.warning("聊天提供商 tryingopen 注册失败（降级跳过）: %s", e)


async def startup_all() -> None:
    bootstrap()
    for p in registry.providers.values():
        try:
            await p.startup()
        except Exception as e:
            log.warning("提供商 %s 启动失败（可忽略，降级）: %s", p.prefix, e)
    for p in registry.chat_providers.values():
        try:
            await p.startup()
        except Exception as e:
            log.warning("聊天提供商 %s 启动失败（可忽略，降级）: %s", p.prefix, e)


async def shutdown_all() -> None:
    for p in registry.providers.values():
        try:
            await p.shutdown()
        except Exception as e:
            log.warning("提供商 %s 停止失败: %s", p.prefix, e)
    for p in registry.chat_providers.values():
        try:
            await p.shutdown()
        except Exception as e:
            log.warning("聊天提供商 %s 停止失败: %s", p.prefix, e)
