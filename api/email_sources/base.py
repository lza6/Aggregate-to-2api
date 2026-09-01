"""邮箱源统一基类（P2-4 v7.3 自 api/email_pool.py 拆分）。

所有邮箱源适配器继承 BaseMailSource：统一的建箱/收件接口 + 退避/打分/健康度管理。
logger 名保持 "email_pool"，与拆分前日志前缀一致（日志检索不受影响）。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

# 子源共用同一 logger 名（与拆分前 email_pool.py 一致，日志前缀不变）
log = logging.getLogger("email_pool")


# ── 规范基类 ──────────────────────────────────────────
@dataclass
class BaseMailSource:
    """统一邮箱源抽象基类。"""

    name: str
    session: httpx.AsyncClient | None = field(default=None, repr=False)
    priority: int = 50
    cooldown_until: float = 0.0
    failure_count: int = 0
    success_count: int = 0
    last_error: str | None = None

    async def new_address(self) -> tuple[str, dict]:
        """生成一个新邮箱，返回 (address, state)。state 供收件用。"""
        raise NotImplementedError

    async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
        """取该邮箱收到的邮件列表。"""
        raise NotImplementedError

    def is_available(self) -> bool:
        """检查当前邮箱源是否处于可用状态（未在冷却期）。"""
        return time.time() >= self.cooldown_until

    def mark_success(self) -> None:
        """记录一次成功分配或收件。"""
        self.success_count += 1
        self.failure_count = max(0, self.failure_count - 1)
        self.last_error = None

    def mark_failure(self, error: str = "", backoff_seconds: float = 30.0) -> None:
        """记录一次失败，并按指数退避冷却。"""
        self.failure_count += 1
        self.last_error = str(error)
        # 1.5 倍指数退避，最大 600s
        multiplier = 1.5 ** min(self.failure_count - 1, 5)
        backoff = min(backoff_seconds * multiplier, 600.0)
        self.cooldown_until = time.time() + backoff
        log.warning(
            "邮箱源 [%s] 发生故障 (累计 %d 次)，退避 %.1fs: %s",
            self.name,
            self.failure_count,
            backoff,
            error,
        )

    def score(self) -> float:
        """根据优先级、成功率与健康度综合打分。"""
        if not self.is_available():
            # 冷却中扣除大量分数
            return -100.0 + (self.priority * 0.1)
        total = self.success_count + self.failure_count
        rate = (self.success_count + 1) / (total + 2)  # 拉普拉斯平滑
        return (self.priority * 10.0) + (rate * 50.0) - (self.failure_count * 10.0)


# 向后兼容别名
MailSource = BaseMailSource
