"""多提供商统一网关：提供商抽象基类。

每个上游（imagefree / aifreeforever / nanobanana-pro 等）实现一个 Provider：
- 统一能力面：txt2img / img2img / txt2vid（支持哪些由 capability 声明）
- 统一生命周期：提交 → 轮询 → 取产物 URL / 下载
- 统一额度面：余额、每次消耗、健康
- 号池接入：需账号的提供商返回 account_pool 需要的注册/签到/凭据获取接口

v4.4 新增 ChatProvider：文本对话提供商抽象基类（与图像 Provider 平行），
支持流式 SSE 输出 / 思考链 / 工具调用模拟 / 多模态图片输入。
"""

from __future__ import annotations

import abc
import logging
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator

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

    id: str  # 外部暴露 id，如 "nanobanana/nano-banana-pro"
    provider: str  # 提供商前缀，如 "nanobanana"
    upstream_model: str  # 上游真实模型 ID，如 "nano-banana-pro"
    capabilities: tuple[str, ...]
    display_name: str = ""
    description: str = ""
    aspect_ratios: tuple[str, ...] = ("1:1", "3:4", "4:3", "9:16", "16:9")
    resolutions: tuple[str, ...] = ("1K", "2K", "4K")
    credits: int | None = None  # 上游积分费率（None=不适用）
    account_required: bool = False  # 是否需要号池账号
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    status: str  # "completed" | "error"
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
    prefix: str = "base"  # 唯一前缀，模型 id 用
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
    async def generate(
        self,
        model: str,
        prompt: str,
        aspect_ratio: str,
        images: list[bytes] | None = None,
        resolution: str = "1K",
        download: bool = False,
        **kw,
    ) -> GenerationResult:
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
        __import__("logging").getLogger("providers").warning("提供商 %s 标记为 down: %s", self.prefix, reason)

    def mark_up(self) -> None:
        """标记提供商为恢复健康。"""
        self.health_status = "healthy"
        self._healthy = True
        self.last_health_check = __import__("time").time()
        __import__("logging").getLogger("providers").info("提供商 %s 标记为 healthy", self.prefix)

    # ── 代理/号池钩子（有需要时覆写）──────────────
    def needs_proxy_per_request(self) -> bool:
        """每次请求是否需要新出口 IP（每 IP 每日限额的平台必须 True）。"""
        return False

    def needs_account(self) -> bool:
        """是否需要号池账号（积分制、用完即弃的平台必须 True）。"""
        return any(m.account_required for m in self.models.values())


# ── 文本对话（chat）能力枚举 ──────────────────────
CAP_CHAT = "chat"
CAP_CHAT_VISION = "chat_vision"  # 支持图片输入
CAP_CHAT_TOOLS = "chat_tools"  # 支持（模拟的）函数调用


class ChatProvider(abc.ABC):
    """文本对话提供商抽象基类（与图像 Provider 平行，不继承它）。

    接口契约：
    - chat_stream() 逐事件 yield，事件类型固定为以下五种 dict：
        {"type": "text",      "text": str}
        {"type": "reasoning", "text": str}
        {"type": "tool_call", "id": str, "name": str, "arguments": str}   # arguments 为 JSON 字符串
        {"type": "usage",     "usage": {"prompt_tokens": int, "completion_tokens": int,
                                        "total_tokens": int, ["reasoning_tokens": int]}}
        {"type": "finish",    "finish_reason": "stop" | "tool_calls" | ...}
    - chat_collect() 为默认非流式便捷封装（聚合上面五种事件）。
    - 子类自行负责代理轮换 / 限流重试 / 消息格式转换。
    """

    prefix: str = "chat_base"
    display_name: str = "Chat Base"
    base_url: str = ""
    models: dict[str, ModelSpec] = {}

    def __init__(self) -> None:
        self.health_status: str = "unknown"
        self._registry_ref: Registry | None = None

    # ── 生命周期 ──────────────────────────────────
    async def startup(self) -> None:
        """启动钩子：创建 HTTP 客户端、启动模型目录自动同步循环等。"""

    async def shutdown(self) -> None:
        """停止钩子：取消后台任务、关闭连接。"""

    def supports(self, capability: str) -> bool:
        return any(capability in m.capabilities for m in self.models.values())

    # ── 模型目录（动态同步）───────────────────────
    def all_models(self) -> list[ModelSpec]:
        return list(self.models.values())

    @abc.abstractmethod
    async def refresh_models(self) -> int:
        """从上游刷新模型目录（供后台定时同步调用）。返回当前模型数。"""

    # ── 核心接口（子类实现）───────────────────────
    @abc.abstractmethod
    def chat_stream(
        self,
        model: str,
        messages: list[dict],
        tools: list | None = None,
        tool_choice: Any = None,
        effort: str = "balanced",
        **kw,
    ) -> AsyncIterator[dict]:
        """流式聊天入口（异步生成器）。messages 为 OpenAI 格式（role/content）。"""

    async def chat_collect(
        self,
        model: str,
        messages: list[dict],
        tools: list | None = None,
        tool_choice: Any = None,
        effort: str = "balanced",
        **kw,
    ) -> dict:
        """非流式聚合：收集全部事件返回完整结果。"""
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[dict] = []
        usage: dict | None = None
        finish_reason = "stop"
        async for ev in self.chat_stream(model, messages, tools=tools, tool_choice=tool_choice, effort=effort, **kw):
            etype = ev.get("type")
            if etype == "text":
                text_parts.append(ev.get("text", ""))
            elif etype == "reasoning":
                reasoning_parts.append(ev.get("text", ""))
            elif etype == "tool_call":
                tool_calls.append(
                    {
                        "id": ev.get("id") or f"call_{int(time.time()*1000):x}",
                        "type": "function",
                        "function": {"name": ev.get("name", ""), "arguments": ev.get("arguments") or "{}"},
                    }
                )
                finish_reason = "tool_calls"
            elif etype == "usage":
                usage = ev.get("usage")
            elif etype == "finish":
                finish_reason = ev.get("finish_reason", finish_reason)
        out = {
            "text": "".join(text_parts),
            "reasoning": "".join(reasoning_parts),
            "usage": usage or {},
            "finish_reason": finish_reason,
            # 成本（USD）：tryingopen 免费为 0；付费渠道可覆写/在 chat_stream 事件携带 cost_usd
            "cost_usd": 0.0,
        }
        if tool_calls:
            out["tool_calls"] = tool_calls
        return out

    # ── 额度 / 健康 ───────────────────────────────
    async def credits(self) -> int | None:
        """当前可用额度估算。None=不适用。"""
        return None

    async def health(self) -> dict:
        return {"healthy": self.health_status != "down", "note": ""}

    async def health_check(self) -> str:
        return "healthy"

    def mark_down(self, reason: str) -> None:
        self.health_status = "down"
        log.warning("ChatProvider %s 标记为 down: %s", self.prefix, reason)

    def mark_up(self) -> None:
        self.health_status = "healthy"
