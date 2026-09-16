"""P2-10: 健康自诊断报告聚合。

聚合七个维度（全部只读，复用既有 metrics/status 快照，不新增采集，不触发真实
付费上游调用）：

- ``providers``：各 provider 成功率 / 时延（adaptive_router 节点快照）
- ``account_pool``：各提供商号池水位（ok/dead/cooling 计数）
- ``email_pool``：邮箱池水位（总数 / by_status / 可用源）
- ``solver``：cf_solver 联邦状态（solver_guard 快照）
- ``queue``：队列积压（pending 总数 + 各优先级）
- ``runtime``：进程内存（psutil/resource 尽力而为）、SSE 活动连接数、worker 数
- ``cost``：成本预测（cost_forecast.predict_budget_burn 输出）

每项独立 try/except：单项采集失败降级为 ``{"error": ...}``，不整端点 500。
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

log = logging.getLogger("health_report")

# 队列优先级标签（与 engine.submit_priority 口径一致：0=admin, 1=paid/high, 2=normal）
_QUEUE_PRIORITIES = (0, 1, 2)
_QUEUE_PRIORITY_LABELS = {0: "admin", 1: "high", 2: "normal"}


def _error_item(e: Exception) -> dict[str, Any]:
    """采集失败的降级字段（仅暴露异常类型+消息，不泄露调用栈）。"""
    return {"error": f"{type(e).__name__}: {e}"[:500]}


# ── 各维度采集（模块级函数，便于测试替换 / 单源失败注入）──────────────────


def _collect_providers(registry: Any) -> dict[str, Any]:
    """各 provider 成功率 / 时延（读 adaptive_router.node_snapshot）。"""
    nodes = registry.adaptive_router.node_snapshot()
    out: dict[str, Any] = {}
    for pid, st in nodes.items():
        ok = int(st.get("success_count") or 0)
        fail = int(st.get("failure_count") or 0)
        total = ok + fail
        out[pid] = {
            "success_count": ok,
            "failure_count": fail,
            "success_rate": round(ok / total, 4) if total else None,
            "ewma_latency_ms": st.get("ewma_latency_ms"),
            "circuit_state": st.get("circuit_state"),
            "consecutive_failures": st.get("consecutive_failures"),
            "in_flight_requests": st.get("in_flight_requests"),
        }
    return {"count": len(out), "nodes": out}


async def _collect_account_pool() -> dict[str, Any]:
    """各提供商号池水位（counts() 全状态细分）。"""
    from .account_pool import account_pool  # noqa: PLC0415

    counts = await account_pool.counts()
    out = {prov: dict(c) for prov, c in counts.items()}
    total = sum(
        int(c.get("ok") or 0) + int(c.get("dead") or 0) for c in counts.values()
    )
    return {"count": len(out), "total_ok": total, "by_provider": out}


async def _collect_email_pool() -> dict[str, Any]:
    """邮箱池水位（email_pool.stats()）。"""
    from .email_pool import email_pool  # noqa: PLC0415

    return await email_pool.stats()


def _collect_solver(solver_guard: Any) -> dict[str, Any]:
    """cf_solver 联邦状态（solver_guard.snapshot()）。"""
    snap = solver_guard.snapshot()
    return {
        "status": snap.get("solver_status"),
        "node_count": snap.get("node_count"),
        "healthy_node_count": snap.get("healthy_node_count"),
        "circuit_open": snap.get("circuit_open"),
        "window_success_rate": snap.get("window_success_rate"),
        "window_solve_count": snap.get("window_solve_count"),
        "consecutive_failures": snap.get("consecutive_failures"),
        "solve_total": snap.get("solve_total"),
        "solve_success_total": snap.get("solve_success_total"),
        "rejected_total": snap.get("rejected_total"),
    }


def _collect_queue(engine: Any) -> dict[str, Any]:
    """队列积压（engine.snapshot() + 各优先级计数）。"""
    snap = engine.snapshot()
    priority_counts: dict[str, Any] = {}
    queue = getattr(engine, "queue", None)
    if queue is not None and hasattr(queue, "count"):
        for p in _QUEUE_PRIORITIES:
            try:
                priority_counts[_QUEUE_PRIORITY_LABELS.get(p, str(p))] = queue.count(p)
            except Exception:  # noqa: BLE001
                priority_counts[_QUEUE_PRIORITY_LABELS.get(p, str(p))] = None
    return {
        "queued": snap.get("queued", 0),
        "processing": snap.get("processing", 0),
        "queue_capacity": snap.get("queue_capacity"),
        "workers": snap.get("workers", 0),
        "by_priority": priority_counts,
    }


def _memory_report() -> dict[str, Any]:
    """进程内存采样（psutil 优先，resource 备选，均不可用则降级不报错）。"""
    try:
        import psutil  # noqa: PLC0415

        vm = psutil.virtual_memory()
        proc = psutil.Process()
        return {
            "available": True,
            "rss_mb": round(proc.memory_info().rss / 1048576.0, 1),
            "system_total_mb": round(vm.total / 1048576.0, 1),
            "system_used_percent": vm.percent,
        }
    except Exception:  # noqa: BLE001
        pass
    try:
        import resource  # noqa: PLC0415

        if hasattr(resource, "getrusage"):
            rss_kb = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            return {"available": True, "rss_kb": rss_kb}
    except Exception:  # noqa: BLE001
        pass
    return {
        "available": False,
        "rss_mb": None,
        "note": "psutil/resource 均不可用，跳过进程内存采样",
    }


def _collect_runtime(engine: Any, hub: Any) -> dict[str, Any]:
    """运行时：内存 / SSE 活动连接数 / worker 数 / 运行时长。"""
    snap = engine.snapshot()
    sse_active = 0
    if hasattr(hub, "active_subscription_count"):
        try:
            sse_active = hub.active_subscription_count()
        except Exception:  # noqa: BLE001
            sse_active = None
    return {
        "memory": _memory_report(),
        "sse_active_connections": sse_active,
        "workers": snap.get("workers", 0),
        "uptime_seconds": snap.get("uptime_seconds"),
    }


async def _collect_cost() -> dict[str, Any]:
    """成本预测（predict_budget_burn 输出，budget 来自 IF_COST_BUDGET_USD）。"""
    from . import config as _cfg  # noqa: PLC0415
    from .chat_usage import chat_usage_tracker as _tracker  # noqa: PLC0415
    from .cost_forecast import predict_budget_burn  # noqa: PLC0415

    daily_costs = (
        await _tracker.cost_daily(30) if hasattr(_tracker, "cost_daily") else []
    )
    budget = float(_cfg.IF_COST_BUDGET_USD or 0.0)
    return predict_budget_burn(daily_costs, budget)


# ── 汇总 ────────────────────────────────────────────────────────────


async def build_health_report() -> dict[str, Any]:
    """聚合七维健康自诊断报告。

    单项采集抛异常 → 该项降级 ``{"error": ...}``，其余维度照常返回，不整端点 500。
    """

    async def _safe(name: str, coro: Any) -> dict[str, Any]:
        try:
            return await coro
        except Exception as e:  # noqa: BLE001
            log.warning("health-report 采集 [%s] 失败: %s", name, e)
            return _error_item(e)

    def _safe_sync(name: str, fn: Any) -> dict[str, Any]:
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            log.warning("health-report 采集 [%s] 失败: %s", name, e)
            return _error_item(e)

    from .meta import engine, registry  # noqa: PLC0415
    from .solver_guard import solver_guard  # noqa: PLC0415
    from .sse_events import hub  # noqa: PLC0415

    return {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "providers": _safe_sync("providers", lambda: _collect_providers(registry)),
        "account_pool": await _safe("account_pool", _collect_account_pool()),
        "email_pool": await _safe("email_pool", _collect_email_pool()),
        "solver": _safe_sync("solver", lambda: _collect_solver(solver_guard)),
        "queue": _safe_sync("queue", lambda: _collect_queue(engine)),
        "runtime": _safe_sync("runtime", lambda: _collect_runtime(engine, hub)),
        "cost": await _safe("cost", _collect_cost()),
    }


# ── Markdown 可读格式 ───────────────────────────────────────────────


def _md_section(title: str, value: Any) -> list[str]:
    """把任意维度值格式化为可读 Markdown 行（嵌套 dict 递归展开）。"""
    lines = [f"### {title}"]
    if isinstance(value, dict) and "error" in value and set(value) == {"error"}:
        lines.append(f"`{value['error']}`")
        return lines

    def _render(v: Any, indent: str = "- ") -> list[str]:
        out: list[str] = []
        if isinstance(v, dict):
            for k, item in v.items():
                if isinstance(item, (dict, list)):
                    out.append(f"{indent}**{k}**")
                    out.extend(_render(item, "  " + indent))
                else:
                    out.append(f"{indent}**{k}**: {_fmt(item)}")
        elif isinstance(v, list):
            out.append(f"{indent}{_fmt(v)}")
        else:
            out.append(f"{indent}{_fmt(v)}")
        return out

    lines.extend(_render(value))
    return lines


def _fmt(item: Any) -> str:
    if item is None:
        return "n/a"
    if isinstance(item, float):
        return f"{item:.4g}".rstrip("0").rstrip(".")
    return str(item)


def format_health_report_md(report: dict[str, Any]) -> str:
    """把健康报告转成可读 Markdown（供 ``?format=md`` 输出 / 工单贴图）。"""
    out = ["# 健康自诊断报告", ""]
    out.append(f"- **生成时间**: {report.get('generated_at', 'n/a')}")
    out.append("")
    simple = {k: v for k, v in report.items() if k != "generated_at"}
    for section, value in simple.items():
        out.extend(_md_section(section, value))
        out.append("")
    return "\n".join(out).strip() + "\n"


__all__ = [
    "build_health_report",
    "format_health_report_md",
    "_collect_providers",
    "_collect_account_pool",
    "_collect_email_pool",
    "_collect_solver",
    "_collect_queue",
    "_collect_runtime",
    "_collect_cost",
]
