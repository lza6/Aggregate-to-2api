"""查询类只读端点（P0-7 拆分自 admin.py）。

函数名与原 admin.py 一致，`from api.routes.admin import metrics` 仍可拿到 `metrics`
函数对象。共享 `router` 单例来自 `_common`（query/write 同一个 router，路由直接注册其上）。
"""

from __future__ import annotations

import hashlib
import hmac
import inspect
import os
import time
from pathlib import Path

from fastapi import Query, Request, WebSocket
from fastapi.responses import FileResponse, PlainTextResponse, Response

from ... import config
from ...audit import audit_log
from ...auth import check_admin_key
from ...errors import AppError, ErrorCodes
from ...log_buffer import log_buffer as log_buffer_handler
from ...log_ws import register_ws, unregister_ws
from ...meta import _SLOW_PAGE, _uptime_human, db, engine, gallery_cache, registry
from ...metrics_ext import imagefree_metrics as metrics_v2
from ...provider_probe import provider_probe
from ...slow_log import slow_log as _slow_log
from ...solver_guard import solver_guard
from ._common import router


@router.get("/v1/models")
@router.get("/v1/model")  # 兼容单数别名，防止用户把路径写错返回 404
async def models():
    """全提供商模型列表。

    返回同时兼容两套契约：
    - `items` / `count`：本服务前端 admin 面板使用的自有分组格式；
    - `data` / `object`：OpenAI 标准 `/v1/models` 契约（Cherry Studio、OpenAI SDK、
      Cursor、NextChat 等客户端按此解析模型列表，缺 `data` 字段会提示"检测不到模型"）。
    """
    from ...providers.registry import bootstrap as providers_bootstrap  # noqa: PLC0415

    providers_bootstrap()
    groups = registry.grouped()
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
    from ...providers.registry import bootstrap as providers_bootstrap  # noqa: PLC0415

    providers_bootstrap()
    summary = registry.provider_summary()
    probes = provider_probe.snapshot().get("providers") or {}

    for prefix in summary:
        p = registry.providers.get(prefix)
        if p is None:
            continue
        try:
            c = await p.credits()
            summary[prefix]["credits"] = c
        except Exception:  # noqa: BLE001
            summary[prefix]["credits"] = None
        if prefix in probes:
            summary[prefix]["probe"] = probes[prefix]

    return {
        "items": summary,
        "count": len(summary),
        "last_probe_time": provider_probe.last_probe_time,
    }


@router.get("/v1/cost")
async def cost_overview():
    """成本可视化（M6-F3）：月成本 / 今日成本 / 预算余量 / 燃烧率 / 月度趋势 / by_provider / by_model。

    - token 成本来自 chat_usage（cost_usd 列，免费渠道为 0）；
    - 图片成本估算 = account_pool.cost_summary(credits_used_total) × IF_USD_PER_CREDIT（0=不估算）；
    - budget 来自 IF_COST_BUDGET_USD（0=不启用成本告警）。
    """
    from ... import account_pool as _account_pool  # noqa: PLC0415
    from ...chat_usage import chat_usage_tracker as _tracker  # noqa: PLC0415

    now = time.time()
    today_start = time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))

    if hasattr(_tracker, "cost_usd_for_range"):
        token_mtd = await _tracker.cost_usd_for_range(now - 30 * 86400, now)
        token_today = await _tracker.cost_usd_for_range(today_start, now)
    else:
        token_mtd = 0.0
        token_today = 0.0

    image_cost = 0.0
    image_credits_used = 0
    image_images = 0
    try:
        _raw_cs = await _account_pool.account_pool.cost_summary("nanobanana")
        cs = await _raw_cs if inspect.isawaitable(_raw_cs) else _raw_cs
        image_credits_used = cs.get("total_credits_used", 0)
        image_images = cs.get("total_images_used", 0)
        image_cost = float(image_credits_used) * float(config.IF_USD_PER_CREDIT or 0.0)
    except Exception:  # noqa: BLE001
        pass

    month_to_date = round(float(token_mtd) + image_cost, 6)
    today_usd = round(float(token_today), 6)
    budget = float(config.IF_COST_BUDGET_USD or 0.0)
    if budget > 0:
        remaining_pct = max(0.0, (1.0 - month_to_date / budget) * 100)
        over_budget = month_to_date >= budget
        burn_rate_warning = month_to_date >= budget * 0.8
    else:
        remaining_pct = 100.0
        over_budget = False
        burn_rate_warning = False

    monthly = await _tracker.cost_monthly(12) if hasattr(_tracker, "cost_monthly") else []
    monthly_by_provider = await _tracker.cost_by_provider(12) if hasattr(_tracker, "cost_by_provider") else []
    monthly_by_model = await _tracker.cost_by_provider_model(12) if hasattr(_tracker, "cost_by_provider_model") else []

    nb_found = False
    for row in monthly_by_provider:
        if row.get("provider") == "nanobanana":
            row["cost_usd"] = round(float(row.get("cost_usd", 0.0)) + image_cost, 6)
            row["credits_used"] = image_credits_used
            row["images"] = image_images
            nb_found = True
    if not nb_found and (image_cost > 0 or image_credits_used > 0):
        monthly_by_provider.append({
            "provider": "nanobanana",
            "calls": 0,
            "cost_usd": round(image_cost, 6),
            "tokens": 0,
            "credits_used": image_credits_used,
            "images": image_images,
        })

    return {
        "month_to_date_usd": month_to_date,
        "today_usd": today_usd,
        "budget_usd": budget,
        "budget_remaining_pct": round(remaining_pct, 2),
        "over_budget": over_budget,
        "burn_rate_warning": burn_rate_warning,
        "monthly": monthly,
        "by_provider": monthly_by_provider,
        "by_model": monthly_by_model,
        "image_cost_usd_mtd": round(image_cost, 6),
        "note": (
            "成本口径：token 成本取 chat_usage.cost_usd 聚合；"
            "图片成本 = 号池累计积分 × IF_USD_PER_CREDIT（默认 0 不估算）。"
            "预算 0 时不启用成本告警。"
        ),
    }


@router.get("/v1/cost-forecast", include_in_schema=False)
async def cost_forecast(request: Request):
    """P3-D3: 成本预算燃烧预测（管理 Key 鉴权）。

    基于近 30 天 chat_usage 日级 cost_usd 历史，按当前日均消耗速率预测何时
    超出 IF_COST_BUDGET_USD 阈值。预算=0 时 disabled=True，前端降级显示"未设预算"。

    口径与 /v1/cost 一致——token 成本来自 chat_usage.cost_usd 按天聚合；图片成本
    为累计折算值（无日级历史），未纳入趋势预测。纯本地 DB 查询 + 数学预测，不调用
    付费 API，不改 DB schema。
    """
    check_admin_key(request, scope="cost-forecast")
    from ...chat_usage import chat_usage_tracker as _tracker  # noqa: PLC0415
    from ...cost_forecast import predict_budget_burn  # noqa: PLC0415

    daily_costs = (
        await _tracker.cost_daily(30) if hasattr(_tracker, "cost_daily") else []
    )
    budget = float(config.IF_COST_BUDGET_USD or 0.0)
    return predict_budget_burn(daily_costs, budget)


@router.get("/v1/account-pool")
async def account_pool_dashboard(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=128),
):
    """号池看板与分页账号明细。"""
    from ...account_pool import account_pool  # noqa: PLC0415
    from ...email_pool import email_pool  # noqa: PLC0415
    from ...registerer import STAGE_LABELS  # noqa: PLC0415

    page_data = await account_pool.list_page(
        "nanobanana",
        None,
        page,
        page_size,
        search,
    )
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
    growth = await account_pool.growth_stats("nanobanana")
    cost = await account_pool.cost_summary("nanobanana")
    desensitized = []
    now_ts = time.time()
    for item in page_data["items"]:
        em = item.get("email", "")
        parts = em.split("@")
        safe_em = (parts[0][:3] + "***@" + parts[1]) if len(parts) == 2 else em
        created = item.get("created_at")
        desensitized.append(
            {
                "email": safe_em,
                "credits": item.get("credits", 0),
                "status": item.get("status", "ok"),
                "created_at": created,
                "checkin_at": item.get("checkin_at"),
                "register_ip": item.get("register_ip"),
                "checkin_total": int(item.get("checkin_total") or 0),
                "checkin_cycle_day": int(item.get("checkin_cycle_day") or 0),
                "credits_earned_total": int(item.get("credits_earned_total") or 0),
                "next_claim_at": item.get("next_claim_at"),
                "age_days": round((now_ts - created) / 86400.0, 1) if created else None,
                "credits_used_total": int(item.get("credits_used_total") or 0),
                "images_used": int(item.get("images_used") or 0),
                "last_used_at": item.get("last_used_at"),
            }
        )
    return {
        "accounts": await account_pool.dashboard(),
        "growth_stats": growth,
        "cost_summary": cost,
        "email_pool": await email_pool.stats(),
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
    from ... import base64_store  # noqa: PLC0415

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


def _gallery_auth(password: str | None) -> None:
    """画廊鉴权：签名 URL 优先，回退静态密码，皆空则开放。"""
    secret = config.IF_GALLERY_SIGNING_SECRET
    if secret and password:
        if _gallery_verify_sig(password, secret):
            return
        raise AppError(ErrorCodes.UNAUTHORIZED, "画廊链接已过期或签名无效", 403)
    pwd = config.IF_GALLERY_PASSWORD
    if pwd:
        if not password or not hmac.compare_digest(password, pwd):
            raise AppError(ErrorCodes.UNAUTHORIZED, "画廊密码错误", 403)


def _gallery_signed_url(limit: int, secret: str, ttl: int) -> str:
    """签发 /v1/gallery?limit=..&exp=..&sig=.. 签名 URL（token 用 exp:sig 紧凑格式）。"""
    exp = int(time.time()) + max(1, int(ttl))
    sig = hmac.new(secret.encode(), str(exp).encode(), hashlib.sha256).hexdigest()
    token = f"{exp}:{sig}"
    return f"/v1/gallery?limit={limit}&password={token}"


def _gallery_verify_sig(token: str, secret: str) -> bool:
    """校验签名 token（'<exp>:<sig>'）。exp 过期即拒；sig 与重算一致（常数时间）。"""
    try:
        exp_str, _, sig = token.partition(":")
        exp = int(exp_str)
    except (ValueError, TypeError):
        return False
    if exp < int(time.time()):
        return False
    expected = hmac.new(secret.encode(), exp_str.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


@router.get("/v1/gallery")
async def gallery(
    limit: int = Query(config.GALLERY_LIMIT, ge=1, le=100), password: str | None = Query(None)
):
    """最近完成的 N 条作品（画廊）。

    鉴权（P1-1 签名 URL 加固）：
    - 优先校验签名 URL：exp + HMAC-SHA256(sig) token（'<exp>:<sig>' 作 password 传入）。
    - 未配签名密钥时回退旧静态密码 IF_GALLERY_PASSWORD（向后兼容）。
    - 两者皆空：画廊开放（向后兼容）。
    """
    _gallery_auth(password)
    cache_key = f"gallery:{limit}"
    cached = await gallery_cache.get(cache_key)
    if cached is not None:
        return cached
    items = await db.recent_images(limit)
    out = []
    for t in items:
        out.append(
            {
                "image_url": t["image_url"],
                "image_mime": t.get("image_mime"),
                "prompt": t["prompt"],
                "aspect_ratio": t["aspect_ratio"],
                "duration_sec": t["duration_sec"],
                "finished_at": t["finished_at"],
            }
        )
    result = {"items": out, "count": len(out)}
    await gallery_cache.set(cache_key, result)
    return result


@router.get("/v1/gallery/sign", include_in_schema=False)
async def gallery_sign(request: Request, limit: int = Query(config.GALLERY_LIMIT, ge=1, le=100)):
    """签发画廊访问 URL（管理 Key 鉴权）。"""
    check_admin_key(request, scope="gallery-sign")
    secret = config.IF_GALLERY_SIGNING_SECRET
    if not secret:
        raise AppError(ErrorCodes.BAD_REQUEST, "未配置画廊签名密钥（IF_GALLERY_SIGNING_SECRET）", 400)
    url = _gallery_signed_url(limit, secret, config.IF_GALLERY_SIGNING_TTL)
    return {"url": url, "expires_in": config.IF_GALLERY_SIGNING_TTL}


@router.get("/v1/errors")
async def errors(limit: int = Query(20, ge=1, le=100)):
    """最近失败的请求明细。"""
    items = await db.recent_errors(limit)
    out = []
    for t in items:
        out.append(
            {
                "id": t["id"],
                "status": t["status"],
                "error": t["error"],
                "prompt_preview": (t["prompt"] or "")[:60],
                "aspect_ratio": t["aspect_ratio"],
                "duration_sec": t["duration_sec"],
                "created_at": t["created_at"],
            }
        )
    total = len(out)
    return {"items": out, "count": total, "total": total}


@router.get("/v1/errors/aggregates", include_in_schema=False)
async def error_aggregates():
    """P0-P1 分层错误码聚合计数。"""
    from ...error_tracker import snapshot, watched_codes  # noqa: PLC0415

    counts = snapshot()
    return {
        "watched": list(watched_codes()),
        "counts": counts,
        "total": sum(counts.values()),
    }


@router.post("/v1/errors/frontend", include_in_schema=False)
async def report_frontend_error(request: Request):
    """前端错误遥测上报（D5）。"""
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise AppError(ErrorCodes.BAD_REQUEST, f"请求体需为合法 JSON: {exc}", 422) from exc
    if not isinstance(body, dict):
        raise AppError(ErrorCodes.BAD_REQUEST, "请求体需为对象", 422)
    code = str(body.get("code") or "").strip()[:32] or "FE.UNKNOWN"
    if not code.startswith("FE."):
        code = f"FE.{code}"
    message = str(body.get("message") or "")[:500]
    stack = str(body.get("stack") or "")[:2000] or None
    url = str(body.get("url") or "")[:500] or None
    ua = request.headers.get("user-agent", "")[:300] or None
    from ...error_tracker import record_frontend_error  # noqa: PLC0415

    record_frontend_error(code=code, message=message, stack=stack, url=url, ua=ua)
    return {"ok": True, "code": code}


@router.get("/v1/errors/frontend", include_in_schema=False)
async def frontend_errors_snapshot():
    """前端错误聚合查看。"""
    from ...error_tracker import frontend_snapshot  # noqa: PLC0415

    return frontend_snapshot()


@router.get("/metrics", include_in_schema=False)
async def metrics():
    snap = engine.snapshot()
    ov = await db.stats_overview()
    ssnap = solver_guard.snapshot()
    body = metrics_v2(snap, ov, ssnap)
    return PlainTextResponse(body, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/v1/logs")
async def get_logs(request: Request, lines: int = Query(50, ge=1, le=200)):
    """返回最近 N 行日志（v7.7.8 公益只读开放）。"""
    return {"logs": log_buffer_handler.snapshot(lines)}


@router.websocket("/v1/logs/ws")
async def log_websocket(websocket: WebSocket):
    """WebSocket 实时日志推送（v7.7.8 公益只读开放）。"""
    await register_ws(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except Exception:  # noqa: BLE001
        pass
    finally:
        await unregister_ws(websocket)


@router.get("/v1/proxy-pool")
async def get_proxy_pool(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=500)):
    """代理池实时状态。"""
    from ...proxy_pool import proxy_pool  # noqa: PLC0415

    return proxy_pool.snapshot(page=page, page_size=page_size)


# 邮箱池上游源官网映射
_EMAIL_SOURCE_HOME_URLS: dict[str, str] = {
    "linshi-email": "https://www.linshi-email.com",
    "mail.tm": "https://mail.tm",
    "mail.gw": "https://mail.gw",
    "guerrillamail": "https://www.guerrillamail.com",
    "22.do": "https://22.do",
    "temp-mail": "https://temp-mail.org",
    "temp-mail.io": "https://temp-mail.io",
    "temp.tf": "https://temp.tf",
}


@router.get("/v1/email-sources")
async def email_sources():
    """邮箱池上游源清单（只读）。"""
    from ...email_pool import email_pool  # noqa: PLC0415

    sources = email_pool.get_sources()
    items: list[dict] = []
    for s in sources:
        home = _EMAIL_SOURCE_HOME_URLS.get(s.name)
        if home is None:
            base = getattr(s, "BASE", None) or getattr(s, "API", None)
            home = base or None
        items.append(
            {
                "name": s.name,
                "base_url": home,
                "priority": s.priority,
                "available": s.is_available(),
                "success_count": s.success_count,
                "failure_count": s.failure_count,
                "last_error": s.last_error,
            }
        )
    return {"items": items, "count": len(items)}


@router.get("/v1/proxy-pool/subscribe", include_in_schema=False)
async def get_proxy_subscription(format: str = Query("base64", description="订阅格式：base64 或 raw")):
    """代理订阅一键生成。"""
    from ...geo_ip import generate_subscription_text  # noqa: PLC0415
    from ...proxy_pool import proxy_pool  # noqa: PLC0415

    snap = proxy_pool.snapshot(page=1, page_size=1000)
    items = snap.get("items") or []
    sub_text = generate_subscription_text(
        [item.get("protocols") for item in items if item.get("protocols")], fmt=format
    )
    media_type = "text/plain; charset=utf-8"
    return Response(content=sub_text, media_type=media_type)


@router.get("/v1/routing/records", include_in_schema=False)
async def get_routing_records(
    limit: int = Query(50, ge=1, le=200),
    from_ts: float | None = Query(None, description="只返回 ts >= from_ts 的历史路由决策"),
):
    """自适应路由记录。

    `registry` 经 `api.routes.admin` 动态解析：test_adaptive_router 用
    `monkeypatch.setattr(admin, "registry", FakeRegistry())` 按名字换对象，需在调用时
    从被 patch 的模块取最新引用（`from ._common import *` 拷贝的绑定收不到 patch）。
    """
    from api.routes import admin as _admin  # noqa: PLC0415

    reg = _admin.registry
    return {
        "records": reg.get_routing_records(limit=limit, from_ts=from_ts),
        "nodes": reg.adaptive_router.node_snapshot(),
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
                "trace_id": getattr(s, "trace_id", ""),
                "submit_ms": round(getattr(s, "submit_ms", 0.0), 1),
                "poll_ms": round(getattr(s, "poll_ms", 0.0), 1),
                "created_at": s.created_at,
            }
            for s in reversed(items)
        ],
        "count": len(items),
    }


@router.get("/v1/audit", include_in_schema=False)
async def audit_search(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    action: str | None = Query(None, description="按 action 过滤"),
    actor: str | None = Query(None, description="按 actor 过滤"),
    trace_id: str | None = Query(None, description="按 traceId 过滤（B2 串联）"),
    q: str | None = Query(None, description="detail/target 模糊搜索"),
):
    """B4: 审计日志搜索（管理 Key 保护）。"""
    check_admin_key(request, scope="admin-audit")
    items = audit_log.recent(limit=limit)

    def _match(e: dict) -> bool:
        if action is not None and e.get("action") != action:
            return False
        if actor is not None and e.get("actor") != actor:
            return False
        if trace_id is not None and (e.get("trace_id") or "") != trace_id:
            return False
        if q:
            hay = f"{e.get('detail') or ''} {e.get('target') or ''}"
            if q not in hay:
                return False
        return True

    filtered = [e for e in items if _match(e)]
    return {
        "items": filtered,
        "count": len(filtered),
        "total_scanned": len(items),
        "filters": {"action": action, "actor": actor, "trace_id": trace_id, "q": q},
    }


@router.get("/v1/slow/view", include_in_schema=False)
async def slow_view():
    """慢请求静态看板。"""
    return FileResponse(_SLOW_PAGE, media_type="text/html")


@router.get("/v1/diagnostics")
async def diagnostics():
    """一键体检（零副作用只读）：DB/队列/worker/token 池/代理池/磁盘/慢日志。"""
    import shutil as _shutil  # noqa: PLC0415

    from ...worker_health import worker_health  # noqa: PLC0415

    db_file = Path(config.DB_FILE)
    db_size_mb = round(db_file.stat().st_size / 1024 / 1024, 2) if db_file.exists() else None
    wal_path = Path(str(db_file) + "-wal")
    wal_size_mb = round(wal_path.stat().st_size / 1024 / 1024, 2) if wal_path.exists() else 0.0
    try:
        du = _shutil.disk_usage(str(db_file.parent if db_file.exists() else Path(".")))
        disk_free_gb = round(du.free / 1024**3, 2)
        disk_total_gb = round(du.total / 1024**3, 2)
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
        "slow_log": {"config_threshold_ms": config.IF_SLOW_REQUEST_MS, **_slow_log.stats()},
        "disk": {
            "free_gb": disk_free_gb,
            "total_gb": disk_total_gb,
            "used_percent": disk_used_pct,
            "log_dir_writable": os.access(config.IF_LOG_DIR, os.W_OK) if os.path.isdir(config.IF_LOG_DIR) else False,
        },
        "uptime_seconds": snap["uptime_seconds"],
    }


@router.get("/v1/sse/stats", include_in_schema=False)
async def sse_stats(request: Request):
    """P3-2: SSE 事件流指标看板（只读，需 admin key）。"""
    check_admin_key(request, scope="admin-sse")
    from ...sse_stats import sse_stats as _sse_stats  # noqa: PLC0415

    return _sse_stats.snapshot()
