"""prometheus_client 指标系统（替代手动拼接 /metrics）。

测试安全：pytest 会话可能多次 import 本模块（conftest 清 sys.modules 后重建），
而 prometheus 全局 REGISTRY 不会清——重复注册会抛 Duplicated timeseries。
统一走 _metric 工厂：已注册同名指标时复用既有 collector。
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY


def _metric(factory, name, doc, labelnames=(), **kw):
    """注册或复用同名指标（模块重导入幂等）。"""
    existing = REGISTRY._names_to_collectors.get(name)
    if existing is not None:
        return existing
    return factory(name, doc, labelnames, **kw) if labelnames else factory(name, doc, **kw)


requests_total = _metric(Counter, "imagefree_requests_total", "累计请求数", ("provider", "status"))
images_total = _metric(Counter, "imagefree_images_total", "累计成功出图数", ("provider",))
errors_total = _metric(Counter, "imagefree_errors_total", "累计失败数", ("provider", "reason"))
errors_by_code = _metric(Counter, "imagefree_errors_by_code", "分层错误码分布（P0-P1 高频）", ("code",))
generate_duration = _metric(Histogram, "imagefree_generate_duration_seconds", "生成耗时", ("provider", "model"), buckets=[1, 5, 10, 30, 60, 120, 300])
processing_gauge = _metric(Gauge, "imagefree_processing", "当前生成中的任务数")
queue_size = _metric(Gauge, "imagefree_queued", "当前排队任务数")
token_pool_watermark = _metric(Gauge, "imagefree_token_pool_watermark", "Token 池水位", ("pool",))
db_rows = _metric(Gauge, "imagefree_db_rows", "请求记录总量")
edit_inflight = _metric(Gauge, "imagefree_edit_inflight", "图生图在途/排队任务数")
uptime_seconds = _metric(Gauge, "imagefree_uptime_seconds", "服务运行时长(秒)")
solve_total = _metric(Counter, "imagefree_solve_total", "Turnstile 求解成功/失败累计数", ("result",))
solve_rejected_total = _metric(Counter, "imagefree_solve_rejected_total", "上游拒绝 token 累计数")
token_wait_timeout_total = _metric(Counter, "imagefree_token_wait_timeout_total", "token 池空 acquire 超时累计数")
solve_duration = _metric(Histogram, "imagefree_solve_duration_seconds", "求解耗时", buckets=[1, 2, 5, 10, 20, 30, 60])
solve_window_success_rate = _metric(Gauge, "imagefree_solve_window_success_rate", "近窗口求解成功率")
solve_consecutive_failures = _metric(Gauge, "imagefree_solve_consecutive_failures", "连续求解失败次数")
solver_circuit_open = _metric(Gauge, "imagefree_solver_circuit_open", "solver 熔断是否开启")
solve_rejected_total = _metric(Counter, "imagefree_solve_rejected_total", "上游拒绝 token 累计数")
token_wait_timeout_total = _metric(Counter, "imagefree_token_wait_timeout_total", "token 池空 acquire 超时累计数")
solve_duration = _metric(Histogram, "imagefree_solve_duration_seconds", "求解耗时", buckets=[1, 2, 5, 10, 20, 30, 60])
solve_window_success_rate = _metric(Gauge, "imagefree_solve_window_success_rate", "近窗口求解成功率")
solve_consecutive_failures = _metric(Gauge, "imagefree_solve_consecutive_failures", "连续求解失败次数")
solver_circuit_open = _metric(Gauge, "imagefree_solver_circuit_open", "solver 熔断是否开启")


def imagefree_metrics(engine_snapshot: dict, stats_overview: dict, solver_snapshot: dict) -> str:
    """用 prometheus_client 生成 /metrics 文本。

    engine_snapshot 需含 processing, queued, uptime_seconds, token_pools, edit_inflight。
    """
    # gauge 重设
    processing_gauge.set(engine_snapshot.get("processing", 0))
    queue_size.set(engine_snapshot.get("queued", 0))
    db_rows.set(stats_overview.get("total_requests", 0))
    uptime_seconds.set(engine_snapshot.get("uptime_seconds", 0))
    edit_inflight.set(engine_snapshot.get("edit_inflight", 0))
    rate = solver_snapshot.get("window_success_rate")
    if rate is not None:
        solve_window_success_rate.set(rate)
    solve_consecutive_failures.set(solver_snapshot.get("consecutive_failures", 0))
    solver_circuit_open.set(1 if solver_snapshot.get("circuit_open") else 0)
    # counter 增量
    requests_total.labels(provider="all", status="completed").inc(stats_overview.get("total_images", 0))
    requests_total.labels(provider="all", status="error").inc(stats_overview.get("total_errors", 0))
    images_total.labels(provider="all").inc(stats_overview.get("total_images", 0))
    errors_total.labels(provider="all", reason="error").inc(stats_overview.get("total_errors", 0))
    solve_total.labels(result="success").inc(solver_snapshot.get("solve_success_total", 0))
    solve_total.labels(result="failure").inc(solver_snapshot.get("solve_failure_total", 0))
    # 分层错误码分布增量（P0-P1 高频；进程内计数，非 DB 累计）
    try:
        from .error_tracker import snapshot as _err_snapshot
        for _code, _n in _err_snapshot().items():
            try:
                errors_by_code.labels(code=_code).inc(int(_n))
            except Exception:
                pass
    except Exception:
        pass
    # token 池水位（每个 pool 独立 label）
    pools = engine_snapshot.get("token_pools", {})
    pool_keys_seen: set[str] = set()
    for label, p in pools.items() if isinstance(pools, dict) else enumerate(pools):
        key = label if isinstance(pools, dict) else p.get("key", "direct") if isinstance(p, dict) else "direct"
        size = p.get("size", 0) if isinstance(p, dict) else 0
        token_pool_watermark.labels(pool=key).set(size)
        pool_keys_seen.add(key)
    if "direct" not in pool_keys_seen:
        token_pool_watermark.labels(pool="direct").set(0)
    return generate_latest(REGISTRY).decode("utf-8")