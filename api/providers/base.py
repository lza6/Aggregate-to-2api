"""多提供商统一网关：提供商抽象基类。

每个上游（imagefree / aifreeforever / nanobanana-pro 等）实现一个 Provider：
- 统一能力面：txt2img / img2img / txt2vid（支持哪些由 capability 声明）
- 统一生命周期：提交 → 轮询 → 取产物 URL / 下载
- 统一额度面：余额、每次消耗、健康
- 号池接入：需账号的提供商返回 account_pool 需要的注册/签到/凭据获取接口
"""
from __future__ import annotations

import abc
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .registry import Registry

log = logging.getLogger("providers")

# M1(审计修复): mock 注册开关。生产（0）时 provider 加载号池会过滤 mock 残留账号，
# 防止测试期 mock-session cookie 泄漏到线上当真实账号使用。
MOCK_REGISTER = os.getenv("IF_MOCK_REGISTER", "0").strip().lower() in {"1", "true", "yes", "on"}


# ── 能力枚举 ──────────────────────────────────────
CAP_TXT2IMG = "txt2img"
CAP_IMG2IMG = "img2img"
CAP_TXT2VID = "txt2vid"
CAP_IMG2VID = "img2vid"


@dataclass(frozen=True)
class ModelSpec:
    """统一模型描述。id = "<provider_prefix>/<真实模型名>"（外部命名契约）。"""
    id: str                 # 外部暴露 id，如 "nanobanana/nano-banana-pro"
    provider: str           # 提供商前缀，如 "nanobanana"
    upstream_model: str     # 上游真实模型 ID，如 "nano-banana-pro"
    capabilities: tuple[str, ...]
    display_name: str = ""
    description: str = ""
    aspect_ratios: tuple[str, ...] = ("1:1", "3:4", "4:3", "9:16", "16:9")
    resolutions: tuple[str, ...] = ("1K", "2K", "4K")
    credits: int | None = None        # 上游积分费率（None=不适用）
    account_required: bool = False    # 是否需要号池账号
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    status: str               # "completed" | "error"
    asset_url: str | None = None
    asset_bytes: bytes | None = None
    asset_mime: str | None = None
    error: str | None = None
    raw: dict | None = None
    proxy_used: str | None = None  # 该请求使用的出口代理（aifreeforever 等每请求轮换代理的提供商填写）


class ProviderError(RuntimeError):
    """提供商调用失败（业务错误，非代码缺陷）。message 面向用户。"""


class ProviderRateLimited(ProviderError):
    """上游限流/风控：调用方可据 is_transient 决定重试策略。"""


class Provider(abc.ABC):
    prefix: str = "base"          # 唯一前缀，模型 id 用
    display_name: str = "Base"
    base_url: str = ""
    # 该提供商固定支持的模型（ID → ModelSpec），注册表自动收集
    models: dict[str, ModelSpec] = {}

    def __init__(self, config: dict | None = None) -> None:
        self.cfg = config or {}
        # 简单健康/额度缓存（healthz 用）
        self._healthy: bool | None = None
        self._last_probe_at = 0.0
        # IMP-22: 健康探测状态
        self.health_status: str = "unknown"  # "unknown" | "healthy" | "degraded" | "down"
        self.last_health_check: float = 0.0
        self.health_check_interval: float = 60.0
        # IMP-18: 由 Registry.register() 设置，避免循环导入
        self._registry_ref: Registry | None = None

    # ── 生命周期 ──────────────────────────────────
    async def startup(self) -> None:
        """启动钩子：加载账号池/代理池、启动签到循环等。"""

    async def shutdown(self) -> None:
        """停止钩子：取消后台任务、关连接。"""

    # ── 能力 ──────────────────────────────────────
    def supports(self, capability: str) -> bool:
        return any(capability in m.capabilities for m in self.models.values())

    # ── 生成（子类实现）───────────────────────────
    @abc.abstractmethod
    async def generate(self, model: str, prompt: str,
                       aspect_ratio: str, images: list[bytes] | None = None,
                       resolution: str = "1K", download: bool = False,
                       **kw) -> GenerationResult:
        """统一生成入口。images 非空=图生图（capability 需含 img2img）。"""

    # ── 额度 / 健康（可选覆写）────────────────────
    async def credits(self) -> int | None:
        """当前可用额度（积分/次数）。None=不适用（如 imagefree 理论无限）。"""
        return None

    async def health(self) -> dict:
        """健康/风控状态摘要（healthz / 前端看板用）。"""
        return {"healthy": True, "note": ""}

    # ── 健康探测（IMP-22）──────────────────────────
    async def health_check(self) -> str:
        """执行健康探测，返回状态字符串。默认返回 "healthy"，子类可覆写实现具体探测逻辑。"""
        return "healthy"

    def mark_down(self, reason: str) -> None:
        """标记提供商为不可用。"""
        self.health_status = "down"
        self._healthy = False
        self.last_health_check = __import__("time").time()
        __import__("logging").getLogger("providers").warning(
            "提供商 %s 标记为 down: %s", self.prefix, reason
        )

    def mark_up(self) -> None:
        """标记提供商为恢复健康。"""
        self.health_status = "healthy"
        self._healthy = True
        self.last_health_check = __import__("time").time()
        __import__("logging").getLogger("providers").info(
            "提供商 %s 标记为 healthy", self.prefix
        )

    # ── 代理/号池钩子（有需要时覆写）──────────────
    def needs_proxy_per_request(self) -> bool:
        """每次请求是否需要新出口 IP（每 IP 每日限额的平台必须 True）。"""
        return False

    def needs_account(self) -> bool:
        """是否需要号池账号（积分制、用完即弃的平台必须 True）。"""
        return any(m.account_required for m in self.models.values())
