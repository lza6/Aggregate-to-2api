"""注册会话状态机、异常分类、退避管理器（P0-5 从 registerer.py 拆出）。

向后兼容：`api.registerer` 旧路径仍 re-export 全部符号。
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .. import config

log = logging.getLogger("registerer")

MOCK_REGISTER = config.MOCK_REGISTER


class RegistrationStage(str, enum.Enum):
    """注册阶段状态枚举。"""

    INIT = "init"
    EMAIL_ALLOCATED = "email_allocated"
    CAPTCHA_SOLVED = "captcha_solved"
    VERIFICATION_SENT = "verification_sent"
    CODE_OR_LINK_RECEIVED = "code_or_link_received"
    LOGGED_IN = "logged_in"
    COMPLETED = "completed"
    FAILED = "failed"


# v6.5.0: 阶段中文显示名（供前端「注册在哪个阶段 + 每阶段耗时」渲染）
STAGE_LABELS: dict[str, str] = {
    "init": "初始化",
    "email_allocated": "分配邮箱",
    "captcha_solved": "求解验证码",
    "verification_sent": "发送验证",
    "code_or_link_received": "收取验证链接",
    "logged_in": "登录换会话",
    "completed": "注册完成",
    "failed": "注册失败",
}


class RegistrationErrorCategory(str, enum.Enum):
    """注册故障分类。"""

    CF_BLOCKED = "cf_blocked"  # CF 阻断 / Turnstile 求解失败 / WAF 拦截
    EMAIL_RATE_LIMITED = "email_rate_limited"  # 邮箱频控 (429 / 验证码收取超时 / 建箱限流)
    IP_BLOCKED = "ip_blocked"  # IP 污染 / 提供商风控 (403 Forbidden / 注册被拒)
    TRANSIENT = "transient"  # 其他瞬态网络错误 (连接抖动 / 超时 / 5xx)


class RegistrationError(Exception):
    """带故障分类与阶段状态的结构化注册异常。"""

    def __init__(
        self,
        message: str,
        category: RegistrationErrorCategory = RegistrationErrorCategory.TRANSIENT,
        stage: RegistrationStage = RegistrationStage.INIT,
        provider: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.category = category
        self.stage = stage
        self.provider = provider
        self.details = details or {}

    def __repr__(self) -> str:
        return (
            f"RegistrationError(provider={self.provider!r}, stage={self.stage.value!r}, "
            f"category={self.category.value!r}, message={self.message!r})"
        )


@dataclass
class RegistrationSession:
    """注册会话上下文与断点快照。"""

    provider: str
    session_id: str = field(default_factory=lambda: f"reg_{int(time.time()*1000)}")
    stage: RegistrationStage = RegistrationStage.INIT
    email: str = ""
    email_source: str = ""
    email_state: dict[str, Any] = field(default_factory=dict)
    proxy_used: str = ""
    captcha_token: str = ""
    verification_token: str = ""
    verification_code: str = ""
    verify_link: str = ""
    session_cookie: str = ""
    password: str = ""
    credits: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_error: str | None = None
    error_category: RegistrationErrorCategory | None = None
    # v6.5.0: 阶段耗时统计（stage 名 -> 进入时间戳），供「注册在哪个阶段 + 每阶段耗时」观测
    stage_history: list[tuple[str, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.stage_history.append((self.stage.value, self.created_at))

    def advance_to(self, stage: RegistrationStage, **kwargs: Any) -> None:
        """推进阶段并更新字段。"""
        self.stage = stage
        self.updated_at = time.time()
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.stage_history.append((stage.value, self.updated_at))
        log.debug("注册会话 [%s][%s] 阶段推进 -> %s", self.provider, self.session_id, stage.value)

    def stage_durations(self) -> dict[str, float]:
        """各阶段耗时（秒）。未走过的阶段不出现；当前未完成阶段以 now-进入 估算。"""
        now = time.time()
        out: dict[str, float] = {}
        hist = self.stage_history
        for i, (stage, ts) in enumerate(hist):
            end = hist[i + 1][1] if i + 1 < len(hist) else now
            out[stage] = round(max(0.0, end - ts), 3)
        return out

    def mark_failed(self, error: str, category: RegistrationErrorCategory) -> None:
        """标记当前会话失败并记录分类。"""
        self.stage = RegistrationStage.FAILED
        self.last_error = error
        self.error_category = category
        self.updated_at = time.time()

    def snapshot(self) -> dict[str, Any]:
        """输出不可变快照供观测与审计。"""
        return {
            "session_id": self.session_id,
            "provider": self.provider,
            "stage": self.stage.value,
            "email": self.email,
            "email_source": self.email_source,
            "has_captcha": bool(self.captcha_token),
            "has_verify_token": bool(self.verification_token),
            "has_code_or_link": bool(self.verification_code or self.verify_link),
            "credits": self.credits,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_error": self.last_error,
            "error_category": self.error_category.value if self.error_category else None,
            "stage_durations": self.stage_durations(),
        }


class AdaptiveRegistrationBackoff:
    """自适应分类退避管理器 (Adaptive Error Backoff)。"""

    def __init__(
        self,
        cf_backoff: float | None = None,
        email_backoff: float | None = None,
        ip_backoff: float | None = None,
        transient_base: float | None = None,
        transient_max: float | None = None,
    ) -> None:
        self.cf_backoff = cf_backoff or getattr(config, "REG_BACKOFF_CF", 30.0)
        self.email_backoff = email_backoff or getattr(config, "REG_BACKOFF_EMAIL", 60.0)
        self.ip_backoff = ip_backoff or getattr(config, "REG_BACKOFF_IP", 120.0)
        self.transient_base = transient_base or getattr(config, "REG_BACKOFF_TRANSIENT_BASE", 2.0)
        self.transient_max = transient_max or getattr(config, "REG_BACKOFF_TRANSIENT_MAX", 30.0)

        self._consecutive_errors: dict[str, int] = {}
        self._last_backoff: dict[str, float] = {}
        self._last_category: dict[str, RegistrationErrorCategory] = {}
        self._stats: dict[str, dict[str, int]] = {}

    def compute_backoff(self, provider: str, category: RegistrationErrorCategory) -> float:
        """根据故障类别与连续失败次数计算退避秒数。"""
        prov_stats = self._stats.setdefault(
            provider, {"cf_blocked": 0, "email_rate_limited": 0, "ip_blocked": 0, "transient": 0, "total": 0}
        )
        prov_stats[category.value] = prov_stats.get(category.value, 0) + 1
        prov_stats["total"] = prov_stats.get("total", 0) + 1

        consecutive = self._consecutive_errors.get(provider, 0) + 1
        self._consecutive_errors[provider] = consecutive
        self._last_category[provider] = category

        if category == RegistrationErrorCategory.CF_BLOCKED:
            backoff = self.cf_backoff
        elif category == RegistrationErrorCategory.EMAIL_RATE_LIMITED:
            backoff = self.email_backoff
        elif category == RegistrationErrorCategory.IP_BLOCKED:
            backoff = self.ip_backoff
        else:
            # TRANSIENT: 2s, 4s, 8s, 16s, ... 最大 30s
            backoff = min(self.transient_base * (2 ** (consecutive - 1)), self.transient_max)

        self._last_backoff[provider] = backoff
        return backoff

    def record_success(self, provider: str) -> None:
        """成功时重置连续失败计数。"""
        self._consecutive_errors[provider] = 0

    def snapshot(self) -> dict[str, Any]:
        """返回退避管理器全局快照。"""
        return {
            "consecutive_errors": dict(self._consecutive_errors),
            "last_backoff": dict(self._last_backoff),
            "last_category": {k: v.value for k, v in self._last_category.items()},
            "stats": dict(self._stats),
        }


# 全局自适应退避单例
adaptive_backoff = AdaptiveRegistrationBackoff()


def _parse_iso_ts(value: Any) -> float | None:
    """把 ISO 时间字符串（如 2026-08-29T07:00:00.000Z）解析成 Unix 时间戳；失败返回 None。"""
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp()
    except Exception:
        return None
