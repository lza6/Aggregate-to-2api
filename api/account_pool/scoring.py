"""MAB 自适应账号评分器（P0-1 从 account_pool.py 拆出）。

独立类，不依赖 AccountPool 私有状态，干净提取。AccountPool 通过组合持有 `_scores: dict[str, AdaptiveAccountScore]`。
向后兼容：`api.account_pool.AdaptiveAccountScore` 旧 import 路径仍可用（见包 __init__）。
"""

from __future__ import annotations


class AdaptiveAccountScore:
    """MAB (Multi-Armed Bandit) 动态评分账号选择器 (基于 EMA 延迟与成功率)。"""

    def __init__(self, email: str):
        self.email = email
        self.ema_latency_ms = 1200.0
        self.success_count = 0
        self.fail_count = 0
        self.consecutive_errors = 0

    def update_result(self, duration_ms: float, is_success: bool):
        alpha = 0.2
        if is_success:
            self.ema_latency_ms = alpha * duration_ms + (1 - alpha) * self.ema_latency_ms
            self.success_count += 1
            self.consecutive_errors = 0
        else:
            self.fail_count += 1
            self.consecutive_errors += 1
            self.ema_latency_ms = max(5000.0, self.ema_latency_ms * 1.5)

    def score(self) -> float:
        total = self.success_count + self.fail_count
        sr = (self.success_count + 1) / (total + 2)  # Laplace 平滑
        latency_score = 1000.0 / max(100.0, self.ema_latency_ms)
        return sr * 50.0 + latency_score * 50.0 - (self.consecutive_errors * 20.0)
