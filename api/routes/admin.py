"""管理面端点（v4.2 拆分：main.py 迁移）。

包含：providers/models/account-pool/proxy-pool/DLQ/logs/stats/gallery/errors/
slow/routing/metrics/diagnostics。
"""
from __future__ import annotations

import hmac
import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter, Query, Request, WebSocket
from fastapi.responses import FileResponse, PlainTextResponse, Response

from .. import config
from ..meta import db, engine, registry, gallery_cache, _SLOW_PAGE, _uptime_human
from ..errors import AppError, ErrorCodes
from ..solver_guard import solver_guard
from ..metrics_ext import imagefree_metrics as metrics_v2
from ..log_ws import register_ws, unregister_ws
from ..log_buffer import log_buffer as log_buffer_handler
from ..audit import audit_log
from ..slow_log import slow_log as _slow_log
from ..provider_probe import provider_probe

router = APIRouter()

log = logging.getLogger("imagefree_api")


@router.get("/v1/models")
@router.get("/v1/model")  # 兼容单数别名，防止用户把路径写错返回 404
async def models():
    """全提供商模型列表。

    返回同时兼容两套契约：
    - `items` / `count`：本服务前端 admin 面板使用的自有分组格式；
    - `data` / `object`：OpenAI 标准 `/v1/models` 契约（Cherry Studio、OpenAI SDK、
      Cursor、NextChat 等客户端按此解析模型列表，缺 `data` 字段会提示"检测不到模型"）。
    """
    from ..providers.registry import bootstrap as providers_bootstrap
    providers_bootstrap()
    groups = registry.grouped()
    # OpenAI 兼容 data 数组：拍平分组为 [{"id","object","created","owned_by"}, ...]
    data_list = [
        {
            "id": m["id"],
            "object": "model",
            "created": 0,
            "owned_by": m["id"].split("/", 1)[0] if "/" in m["id"] else "imagefree",
        }
        for mods in groups.values()
        for m in mods
    ]
    return {
        "object": "list",
        "data": data_list,
        "items": groups,
        "count": len(data_list),
        "note": "模型 id 命名：<提供商前缀>/<上游真实模型名>；capabilities 含 txt2img/img2img/txt2vid",
    }


@router.get("/v1/providers")
async def providers():
    """提供商看板：能力/模型数/账号需求/每请求代理需求/实时余额 + 上游真实探针状态。"""
    from ..providers.registry import bootstrap as providers_bootstrap
    providers_bootstrap()
    summary = registry.provider_summary()
    probes = provider_probe.snapshot().get("providers") or {}

    for prefix, p in registry.providers.items():
        try:
            c = await p.credits()
            summary[prefix]["credits"] = c
        except Exception:
            summary[prefix]["credits"] = None
        if prefix in probes:
            summary[prefix]["probe"] = probes[prefix]

    return {
        "items": summary,
        "count": len(summary),
        "last_probe_time": provider_probe.last_probe_time,
    }


@router.get("/v1/account-pool")
async def account_pool_dashboard(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=128),
):
    """号池看板与分页账号明细。"""
    from ..account_pool import account_pool
    from ..email_pool import email_pool
    from ..registerer import STAGE_LABELS
    page_data = account_pool.list_page(
        provider="nanobanana", page=page, page_size=page_size, search=search,
    )
    # v6.5.0: 最近一次注册会话的阶段画像 + 各阶段耗时（供「注册在哪个阶段/每阶段耗时」渲染）
    reg = account_pool.registerers.get("nanobanana")
    live_stage = None
    if reg is not None:
        snap = getattr(reg, "live_session_snapshot", None)
        if snap:
            live_stage = {
                "stage": snap.get("stage"),
                "stage_label": STAGE_LABELS.get(snap.get("stage"), snap.get("stage")),
                "email": snap.get("email"),
                "email_source": snap.get("email_source"),
                "created_at": snap.get("created_at"),
                "updated_at": snap.get("updated_at"),
                "last_error": snap.get("last_error"),
                "error_category": snap.get("error_category"),
                "stage_durations": snap.get("stage_durations"),
            }
    desensitized = []
    now_ts = time.time()
    for item in page_data["items"]:
        em = item.get("email", "")
        parts = em.split("@")
        safe_em = (parts[0][:3] + "***@" + parts[1]) if len(parts) == 2 else em
        created = item.get("created_at")
        desensitized.append({
            "email": safe_em,
            "credits": item.get("credits", 0),
            "status": item.get("status", "ok"),
            "created_at": created,
            "checkin_at": item.get("checkin_at"),
            "register_ip": item.get("register_ip"),
            # v6.3.4: 签到画像与存活天数（前端直接可渲染）
            "checkin_total": int(item.get("checkin_total") or 0),
            "checkin_cycle_day": int(item.get("checkin_cycle_day") or 0),
            "credits_earned_total": int(item.get("credits_earned_total") or 0),
            "next_claim_at": item.get("next_claim_at"),
            "age_days": round((now_ts - created) / 86400.0, 1) if created else None,
            # v6.5.1: 每账号出图消耗画像（累计消耗积分 / 出图次数 / 最近出图）
            "credits_used_total": int(item.get("credits_used_total") or 0),
            "images_used": int(item.get("images_used") or 0),
            "last_used_at": item.get("last_used_at"),
        })
    return {
        "accounts": account_pool.dashboard(),
        "email_pool": email_pool.stats(),
        "live_registration": live_stage,
        "items": desensitized,
        "items_total": page_data["total"],
        "page": page_data["page"],
        "page_size": page_data["page_size"],
        "total_pages": page_data["total_pages"],
    }


@router.get("/v1/stats")
async def get_stats():
    """总量统计 + 实时并发/排队 + 按日/月拆分 + 平均出图耗时。"""
    overview = await gallery_cache.get("stats:overview")
    if overview is None:
        overview = await db.stats_overview()
        await gallery_cache.set("stats:overview", overview)
    daily = await gallery_cache.get("stats:daily:14")
    if daily is None:
        daily = await db.stats_daily(14)
        await gallery_cache.set("stats:daily:14", daily)
    monthly = await gallery_cache.get("stats:monthly:12")
    if monthly is None:
        monthly = await db.stats_monthly(12)
        await gallery_cache.set("stats:monthly:12", monthly)
    live = engine.snapshot()
    ssnap = solver_guard.snapshot()
    from .. import base64_store  # noqa: PLC0415
    return {
        **overview,
        "processing": live["processing"],
        "queued": live["queued"],
        "queue_capacity": live["queue_capacity"],
        "workers": live["workers"],
        "uptime_seconds": live["uptime_seconds"],
        "uptime_human": _uptime_human(live["uptime_seconds"]),
        "daily": daily,
        "monthly": monthly,
        "base64_gc": base64_store.gc_stats(),
        "solver": {
            "status": ssnap["solver_status"],
            "solve_total": ssnap["solve_total"],
            "solve_success_total": ssnap["solve_success_total"],
            "solve_failure_total": ssnap["solve_failure_total"],
            "solve_avg_seconds": ssnap["solve_avg_seconds"],
            "window_success_rate": ssnap["window_success_rate"],
            "window_solve_count": ssnap["window_solve_count"],
            "window_avg_seconds": ssnap["window_avg_seconds"],
            "consecutive_failures": ssnap["consecutive_failures"],
            "circuit_open": ssnap["circuit_open"],
            "failure_reasons": ssnap["failure_reasons"],
            "rejected_total": ssnap["rejected_total"],
            "token_pools": live["token_pools"],
        },
    }


@router.get("/v1/gallery")
async def gallery(limit: int = Query(config.GALLERY_LIMIT, ge=1, le=100),
                  password: str | None = Query(None)):
    """最近完成的 N 条作品（画廊）。"""
    pwd = config.IF_GALLERY_PASSWORD
    if pwd:
        if not password or not hmac.compare_digest(password, pwd):
            raise AppError(ErrorCodes.UNAUTHORIZED, "画廊密码错误", 403)
    cache_key = f"gallery:{limit}"
    cached = await gallery_cache.get(cache_key)
    if cached is not None:
        return cached
    items = await db.recent_images(limit)
    out = []
    for t in items:
        out.append({
            "image_url": t["image_url"],
            "image_mime": t.get("image_mime"),
            "prompt": t["prompt"],
            "aspect_ratio": t["aspect_ratio"],
            "duration_sec": t["duration_sec"],
            "finished_at": t["finished_at"],
        })
    result = {"items": out, "count": len(out)}
    await gallery_cache.set(cache_key, result)
    return result


@router.get("/v1/errors")
async def errors(limit: int = Query(20, ge=1, le=100)):
    """最近失败的请求明细。"""
    items = await db.recent_errors(limit)
    out = []
    for t in items:
        out.append({
            "id": t["id"],
            "status": t["status"],
            "error": t["error"],
            "prompt_preview": (t["prompt"] or "")[:60],
            "aspect_ratio": t["aspect_ratio"],
            "duration_sec": t["duration_sec"],
            "created_at": t["created_at"],
        })
    total = len(out)
    return {"items": out, "count": total, "total": total}


@router.get("/metrics", include_in_schema=False)
async def metrics():
    snap = engine.snapshot()
    ov = await db.stats_overview()
    ssnap = solver_guard.snapshot()
    body = metrics_v2(snap, ov, ssnap)
    return PlainTextResponse(body, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/v1/logs")
async def get_logs(lines: int = Query(50, ge=1, le=200)):
    """返回最近 N 行日志。"""
    return {"logs": log_buffer_handler.snapshot(lines)}


@router.websocket("/v1/logs/ws")
async def log_websocket(websocket: WebSocket):
    """WebSocket 实时日志推送。"""
    await register_ws(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except Exception:
        pass
    finally:
        await unregister_ws(websocket)


@router.get("/v1/dead-letter-queue")
async def dead_letter_queue(limit: int = Query(20, ge=1, le=100)):
    """死信队列。"""
    items = await db.list_dlq(limit)
    return {"items": items, "count": len(items)}


@router.post("/v1/dead-letter-queue/{task_id}/retry")
async def retry_dlq_task(task_id: str, request: Request):
    """死信队列重试。"""
    client_ip = request.client.host if request.client else "unknown"
    audit_log.record("dlq.retry", client_ip, f"task:{task_id}", "重试死信队列任务")
    if config.IF_DLQ_REQUEUE:
        from ..worker import engine as _engine
        requeued = await _engine.requeue_dlq_task(task_id)
        if not requeued:
            raise AppError(ErrorCodes.BAD_REQUEST,
                           f"任务 {task_id} 重入队失败（不存在或队列已满）", 409)
        await db.retry_dlq(task_id)
        return {"status": "ok",
                "detail": f"任务 {task_id} 已重新入队（pending，等待 worker 处理）"}
    await db.retry_dlq(task_id)
    return {"status": "ok", "detail": f"任务 {task_id} 已从死信队列移除"}


@router.delete("/v1/dead-letter-queue")
async def clear_dlq(request: Request):
    """清空死信队列所有记录。"""
    client_ip = request.client.host if request.client else "unknown"
    audit_log.record("dlq.clear", client_ip, "dlq", "清空死信队列")
    await db.clear_dlq()
    return {"status": "ok", "detail": "死信队列已清空"}


@router.get("/v1/proxy-pool")
async def get_proxy_pool(page: int = Query(1, ge=1),
                         page_size: int = Query(20, ge=1, le=500)):
    """代理池实时状态。"""
    from ..proxy_pool import proxy_pool
    return proxy_pool.snapshot(page=page, page_size=page_size)


@router.get("/v1/proxy-pool/subscribe", include_in_schema=False)
async def get_proxy_subscription(format: str = Query("base64", description="订阅格式：base64 或 raw")):
    """代理订阅一键生成。"""
    from ..proxy_pool import proxy_pool
    from ..geo_ip import generate_subscription_text
    snap = proxy_pool.snapshot(page=1, page_size=1000)
    items = snap.get("items") or []
    sub_text = generate_subscription_text([item.get("protocols") for item in items if item.get("protocols")], fmt=format)
    media_type = "text/plain; charset=utf-8"
    return Response(content=sub_text, media_type=media_type)


@router.get("/v1/routing/records", include_in_schema=False)
async def get_routing_records(limit: int = Query(50, ge=1, le=200)):
    """自适应路由记录。"""
    return {
        "records": registry.get_routing_records(limit=limit),
        "nodes": registry.adaptive_router.node_snapshot(),
    }


@router.get("/v1/slow", include_in_schema=False)
async def get_slow_requests(limit: int = Query(50, ge=1, le=500)):
    """慢请求画像。"""
    items = _slow_log.snapshot()[-limit:]
    return {
        "threshold_ms": config.IF_SLOW_REQUEST_MS,
        "enabled": config.IF_SLOW_LOG_ENABLED,
        "stats": _slow_log.stats(),
        "items": [
            {
                "task_id": s.task_id,
                "model": s.model,
                "provider": s.provider,
                "queue_ms": round(s.queue_ms, 1),
                "wait_token_ms": round(s.wait_token_ms, 1),
                "solve_ms": round(s.solve_ms, 1),
                "upstream_ms": round(s.upstream_ms, 1),
                "retry_ms": round(s.retry_ms, 1),
                "total_ms": round(s.total_ms, 1),
                "slowest_stage": s.slowest_stage(),
                "status": s.status,
                "created_at": s.created_at,
            }
            for s in reversed(items)
        ],
        "count": len(items),
    }


@router.get("/v1/slow/view", include_in_schema=False)
async def slow_view():
    """慢请求静态看板。"""
    return FileResponse(_SLOW_PAGE, media_type="text/html")


@router.get("/v1/diagnostics")
async def diagnostics():
    """一键体检（零副作用只读）：DB/队列/worker/token 池/代理池/磁盘/慢日志。"""
    import shutil as _shutil
    from ..worker_health import worker_health
    db_file = Path(config.DB_FILE)
    db_size_mb = round(db_file.stat().st_size / 1024 / 1024, 2) if db_file.exists() else None
    wal_path = Path(str(db_file) + "-wal")
    wal_size_mb = round(wal_path.stat().st_size / 1024 / 1024, 2) if wal_path.exists() else 0.0
    try:
        du = _shutil.disk_usage(str(db_file.parent if db_file.exists() else Path(".")))
        disk_free_gb = round(du.free / 1024 ** 3, 2)
        disk_total_gb = round(du.total / 1024 ** 3, 2)
        disk_used_pct = round((du.used / du.total) * 100, 1) if du.total else None
    except OSError:
        disk_free_gb = disk_total_gb = disk_used_pct = None
    snap = engine.snapshot()
    ssnap = solver_guard.snapshot()
    return {
        "status": "ok",
        "timestamp": int(time.time()),
        "db": {
            "file": config.DB_FILE,
            "size_mb": db_size_mb,
            "wal_size_mb": wal_size_mb,
            "rows": await db.count(),
            "batch_enabled": config.IF_DB_BATCH_ENABLED,
        },
        "queue": {
            "queued": snap["queued"],
            "capacity": snap["queue_capacity"],
            "admin": engine.queue.count(0),
            "high": engine.queue.count(1),
            "normal": engine.queue.count(2),
            "processing": engine.processing,
        },
        "workers": {**worker_health.summary(), "detail": worker_health.snapshot()},
        "token_pools": engine.token_pool_manager.pools_snapshot(),
        "solver": {
            "status": ssnap["solver_status"],
            "circuit_open": ssnap["circuit_open"],
            "window_success_rate": ssnap["window_success_rate"],
            "avg_solve_seconds": ssnap["solve_avg_seconds"],
        },
        "slow_log": {"config_threshold_ms": config.IF_SLOW_REQUEST_MS,
                     **_slow_log.stats()},
        "disk": {
            "free_gb": disk_free_gb,
            "total_gb": disk_total_gb,
            "used_percent": disk_used_pct,
            "log_dir_writable": os.access(config.IF_LOG_DIR, os.W_OK)
                                if os.path.isdir(config.IF_LOG_DIR) else False,
        },
        "uptime_seconds": snap["uptime_seconds"],
    }