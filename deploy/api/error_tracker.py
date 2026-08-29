"""分层错误码聚合计数（Section 16 可观测性 / P2）。

设计：所有 AppError / 未捕获异常经 handlers 落于此（线程安全计数）。
用途：
- /v1/errors/aggregates 端点展示 P0-P1 错误分布；
- 告警引擎 `error_codes` 上下文据此判断 AUTH.001 等高发码；
- Prometheus `imagefree_errors_by_code` 指标同步增量（metrics_ext）。

独立轻量组件，不引入外部依赖；进程重启即清零（符合诊断数据语义，与 slow_log 一致）。
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_counts: dict[str, int] = {}

# 只关注的高频 P0-P1 错误码（其余归 SYS.001 / other 泛化，避免标签爆炸）
_WATCH_CODES = ("AUTH.001", "AUTH.002", "AUTH.003", "RATE.001", "PROV.001", "SYS.001")


def record(code: str) -> None:
    """记录一次错误（幂等，线程安全）。

    code 为分层格式（如 AUTH.001）；旧版码由 AppError 已解析为分层格式。
    """
    if not code:
        code = "SYS.001"
    with _lock:
        _counts[code] = _counts.get(code, 0) + 1


def watched_codes() -> list[str]:
    """供告警/看板筛选的关注错误码列表。"""
    return list(_WATCH_CODES)


def snapshot() -> dict[str, int]:
    """返回当前错误码计数拷贝（按次数降序）。"""
    with _lock:
        return {k: v for k, v in sorted(_counts.items(), key=lambda kv: -kv[1])}


def count_of(code: str) -> int:
    """单个错误码计数（未出现返回 0）。"""
    with _lock:
        return _counts.get(code, 0)


def reset() -> None:
    """清空（测试/诊断用）。"""
    with _lock:
        _counts.clear()
