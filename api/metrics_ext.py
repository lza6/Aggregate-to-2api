"""prometheus_client 指标系统（替代手动拼接 /metrics）。"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY

requests_total = Counter("imagefree_requests_total", "累计请求数", ["provider", "status"])
images_total = Counter("imagefree_images_total", "累计成功出图数", ["provider"])
errors_total = Counter("imagefree_errors_total", "累计失败数", ["provider", "reason"])
generate_duration = Histogram("imagefree_generate_duration_seconds", "生成耗时", ["provider", "model"], buckets=[1, 5, 10, 30, 60, 120, 300])
processing_gauge = Gauge("imagefree_processing", "当前生成中的任务数")
queue_size = Gauge("imagefree_queued", "当前排队任务数")
token_pool_watermark = Gauge("imagefree_token_pool_watermark", "Token 池水位", ["pool"])
db_rows = Gauge("imagefree_db_rows", "请求记录总量")
edit_inflight = Gauge("imagefree_edit_inflight", "图生图在途/排队任务数")
uptime_seconds = Gauge("imagefree_uptime_seconds", "服务运行时长(秒)")
solve_total = Counter("imagefree_solve_total", "Turnstile 求解成功/失败累计数", ["result"])
solve_duration = Histogram("imagefree_solve_duration_seconds", "求解耗时", buckets=[1, 2, 5, 10, 20, 30, 60])
solve_window_success_rate = Gauge("imagefree_solve_window_success_rate", "近窗口求解成功率")
solve_consecutive_failures = Gauge("imagefree_solve_consecutive_failures", "连续求解失败次数")
solver_circuit_open = Gauge("imagefree_solver_circuit_open", "solver 熔断是否开启")


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
    # token 池水位（每个 pool 独立 label）
    pools = engine_snapshot.get("token_pools", [])
    pool_keys_seen: set[str] = set()
    for p in pools:
        key = p.get("key", "direct") if isinstance(p, dict) else "direct"
        size = p.get("size", 0) if isinstance(p, dict) else 0
        token_pool_watermark.labels(pool=key).set(size)
        pool_keys_seen.add(key)
    if "direct" not in pool_keys_seen:
        token_pool_watermark.labels(pool="direct").set(0)
    return generate_latest(REGISTRY).decode("utf-8")