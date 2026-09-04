"""健康/静态/元信息路由（v4.2 拆分：main.py 迁移）。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse

from .. import config
from ..meta import db, engine
from ..providers import registry
from ..errors import AppError, ErrorCodes
from ..solver_guard import solver_guard
from ..slow_log import slow_log
from ..slo_budget import slo_budget as _slo_engine
from ..health import health_registry
from ..system_spec import system_spec

# 需要在 main 组装的 edit 状态（图生图看板用）
from ..dispatch_edit import _EDIT_PENDING

router = APIRouter()

_TERMS_PAGE = Path(__file__).parent.parent / "static" / "terms.html"
_TERMS_DIR = Path(__file__).parent.parent / "static" / "terms"
_TERMS_MAP = {
    "service": {"title": "服务条款", "url": "/v1/terms/service"},
    "privacy": {"title": "隐私政策", "url": "/v1/terms/privacy"},
    "content": {"title": "内容政策", "url": "/v1/terms/content"},
    "disclaimer": {"title": "免责声明", "url": "/v1/terms/disclaimer"},
}
_HONOR_PAGE = Path(__file__).parent.parent / "static" / "honor.html"
_STATIC_DIR = Path(__file__).parent.parent / "static"
_logo_sm = _STATIC_DIR / "tingfeng-logo-sm.png"
_logo_md = _STATIC_DIR / "tingfeng-logo-md.png"
_zanshang_qr = _STATIC_DIR / "zanshang.jpg"


# v6.5.0：公开首页 / 改为 Vue3 落地页（main.py mount "./landing/dist"）。
# 原单文件 docs.html 交互文档不再挂载到 /，改为由落地页引导至 /admin 与 Swagger /docs。
# 移除本 GET / 路由，避免在 api_router（先注册）中抢占根路径，挡住 landing 挂载。
@router.get("/v1/terms", include_in_schema=False)
async def terms() -> FileResponse:
    """服务条款页面。"""
    return FileResponse(_TERMS_PAGE, media_type="text/html")


@router.get("/v1/terms/index", include_in_schema=False)
async def terms_index() -> list[dict[str, Any]]:
    """服务条款子页面结构化列表。"""
    return [{"slug": slug, "title": meta["title"], "url": meta["url"]} for slug, meta in _TERMS_MAP.items()]


@router.get("/v1/terms/{sub}", include_in_schema=False)
async def terms_sub(sub: str) -> FileResponse:
    """服务条款细分页面：service / privacy / content / disclaimer。"""
    if sub not in _TERMS_MAP:
        raise AppError(ErrorCodes.NOT_FOUND, f"未知的条款页面：{sub}", status_code=404)
    return FileResponse(_TERMS_DIR / f"{sub}.html", media_type="text/html")


@router.get("/v1/honor", include_in_schema=False)
async def honor() -> FileResponse:
    """捐赠页。"""
    return FileResponse(_HONOR_PAGE, media_type="text/html")


@router.get("/v1/honor/data", include_in_schema=False)
async def honor_data() -> dict[str, Any]:
    """捐赠数据接口。"""
    return {
        "status": "ok",
        "title": "支持听风",
        "message": (
            "听风AI（逆向号池）是公益运行的多提供商 AI 图像生成网关，"
            "提供免费、开放的高效出图服务。项目依赖个人时间与服务器成本持续运转，"
            "如果你觉得它对你有所帮助，欢迎扫码支持，每一份心意都是坚持下去的动力。"
        ),
        "qr_path": "/static/zanshang.jpg",
        "contact_wx": "Tf00798",
        "github": "https://github.com/lza6/",
    }


# M5: cf_solver 探活结果 TTL 缓存
_cf_probe_cache: dict[str, Any] = {"ok": False, "at": 0.0}


async def _probe_cf_solver(force: bool = False) -> bool:
    if not force and time.time() - _cf_probe_cache["at"] < config.HEALTHZ_CACHE_TTL:
        return _cf_probe_cache["ok"]  # type: ignore[no-any-return]
    try:
        from urllib.parse import urlsplit

        u = urlsplit(config.CF_SOLVER_URL)
        host, port = u.hostname or "127.0.0.1", u.port or 8001
    except (ValueError, IndexError):
        _cf_probe_cache.update(ok=False, at=time.time())
        return False
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, int(port)), timeout=2.0)
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
        except Exception:
            pass
        _cf_probe_cache.update(ok=True, at=time.time())
        return True
    except Exception:
        _cf_probe_cache.update(ok=False, at=time.time())
        return False


@router.get("/v1/healthz")
async def healthz() -> dict[str, Any]:
    """健康检查：本服务 + cf_solver 可用性 + solver 求解质量 + 统一健康视图（A-04）。"""
    cf_ok = await _probe_cf_solver()
    snap = engine.snapshot()
    ssnap = solver_guard.snapshot()
    await health_registry.check_all()
    _stats = await db.stats_overview()
    _slo = _slo_engine.snapshot(_stats, ssnap, slow_log.stats(), snap)
    return {
        "status": "degraded" if (not cf_ok or ssnap["solver_status"] != "ok") else "ok",
        "cf_solver": "up" if cf_ok else "down",
        "processing": engine.processing,
        "queued": engine.queue.qsize(),
        "queue_capacity": snap["queue_capacity"],
        "workers": snap["workers"],
        "token_pool": engine.token_pool.qsize(),
        "edit_inflight": len(_EDIT_PENDING),
        "db_rows": await db.count(),
        "uptime_seconds": snap["uptime_seconds"],
        "timestamp": int(time.time()),
        "solver_status": ssnap["solver_status"],
        "solve_success_total": ssnap["solve_success_total"],
        "solve_failure_total": ssnap["solve_failure_total"],
        "solve_avg_seconds": ssnap["solve_avg_seconds"],
        "solve_window_success_rate": ssnap["window_success_rate"],
        "solve_window_solve_count": ssnap["window_solve_count"],
        "solve_consecutive_failures": ssnap["consecutive_failures"],
        "solve_last_failure_at": ssnap["last_failure_at"],
        "solver_circuit_open": ssnap["circuit_open"],
        "solve_rejected_total": ssnap["rejected_total"],
        "token_pools": engine.token_pool_manager.pools_snapshot(),
        "slo_budget": _slo,
        "providers": {
            prefix: {
                "status": p.health_status,
                "last_check": getattr(p, "last_health_check", None),
            }
            for prefix, p in registry.providers.items()
        },
        "queue": {
            "admin": engine.queue.count(0),
            "high": engine.queue.count(1),
            "normal": engine.queue.count(2),
            "limits": {
                "admin": config.ADMIN_QUEUE_MAX,
                "high": config.HIGH_QUEUE_MAX,
                "normal": config.NORMAL_QUEUE_MAX,
            },
        },
        "system": system_spec(),
        "log_dir": {
            "path": config.IF_LOG_DIR,
            "writable": os.access(config.IF_LOG_DIR, os.W_OK) if os.path.isdir(config.IF_LOG_DIR) else False,
        },
    }


@router.get("/v1/livez", include_in_schema=True)
async def livez() -> dict[str, Any]:
    """存活探针（liveness）：进程活即 ok，不探任何外部依赖。

    Docker healthcheck 用此端点——停 solver 时 readiness 降级而 liveness 不误杀，
    避免容器被错误重启。
    """
    return {"status": "ok", "timestamp": int(time.time())}


@router.get("/v1/readyz", include_in_schema=True)
async def readyz(response: Response) -> dict[str, Any]:
    """就绪探针（readiness）：聚合依赖探活，任一关键依赖不 ok → 503。

    探活项：cf_solver 可达、solver_guard 熔断状态、DB 可读、队列未堵。
    供上游路由/负载均衡探活，不在 docker healthcheck 使用。
    """
    reasons: list[str] = []

    # (a) cf_solver 可达（复用 TTL 缓存，避免每次 TCP 探活）
    cf_ok = await _probe_cf_solver()
    if not cf_ok:
        reasons.append("cf_solver unreachable")

    # (b) solver_guard 熔断状态
    ssnap = solver_guard.snapshot()
    if ssnap["circuit_open"] or ssnap["solver_status"] != "ok":
        reasons.append(f"solver {ssnap['solver_status']}")

    # (c) DB 可读
    try:
        await db.count()
    except OSError as e:
        reasons.append(f"db unreadable: {type(e).__name__}")
    except Exception as e:  # noqa: BLE001 - 探活端点需兜底所有异常转为 not_ready
        reasons.append(f"db unreadable: {type(e).__name__}")

    # (d) 队列未堵
    snap = engine.snapshot()
    if snap["queued"] >= snap["queue_capacity"]:
        reasons.append("queue saturated")

    response.status_code = 200 if not reasons else 503
    return {
        "status": "ready" if not reasons else "not_ready",
        "reasons": reasons,
        "timestamp": int(time.time()),
    }


@router.get("/v1/system")
async def system_info(request: Request, response: Response) -> dict[str, Any]:
    """服务器规格与自适应并发参数（供前端看板展示）。

    P2-3: ETag 协商缓存——低频变更只读端点，响应体哈希作 ETag；
    客户端带 If-None-Match 且匹配 → 304 Not Modified（省带宽）。
    """
    payload = system_spec()
    etag = '"' + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:32] + '"'
    inm = request.headers.get("if-none-match")
    if inm and inm == etag:
        response.status_code = 304
        response.headers["ETag"] = etag
        return {}  # 304 空 body
    response.headers["ETag"] = etag
    return payload


@router.get("/v1/meta")
async def meta(request: Request, response: Response) -> dict[str, Any]:
    """暴露站点配置，方便调用方集成。

    安全（P0）：此处为公开只读探测端点，**不返回完整 API Key**，仅返回脱敏前缀与鉴权开关。
    需要「站长一键复制完整 Key」走 /v1/chat/auth/status（带管理 Key 鉴权）。

    P2-3: ETag 协商缓存（同 /v1/system——api_key_mask 变化时 ETag 自动失效）。
    """
    from ..auth import public_keymask, auth_enabled

    payload = {
        "sitekey": config.SITEKEY,
        "aspect_ratios": config.ASPECT_RATIOS,
        "supported_resolutions": ["1K", "2K", "4K", "480p", "720p"],
        "gallery_requires_password": bool(config.IF_GALLERY_PASSWORD),
        "auth_enabled": auth_enabled(),
        "api_key_mask": public_keymask(),
    }
    etag = '"' + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:32] + '"'
    inm = request.headers.get("if-none-match")
    if inm and inm == etag:
        response.status_code = 304
        response.headers["ETag"] = etag
        return {}
    response.headers["ETag"] = etag
    return payload


@router.get("/static/zanshang.jpg", include_in_schema=False)
async def zanshang_qr() -> FileResponse:
    if _zanshang_qr.exists():
        return FileResponse(_zanshang_qr, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})
    raise AppError(ErrorCodes.NOT_FOUND, "赞赏码图片不存在", 404)


@router.get("/static/logo.png", include_in_schema=False)
async def logo_small() -> FileResponse:
    if _logo_sm.exists():
        return FileResponse(_logo_sm, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})
    raise AppError(ErrorCodes.NOT_FOUND, "Logo not found", 404)


@router.get("/static/logo-md.png", include_in_schema=False)
async def logo_medium() -> FileResponse:
    if _logo_md.exists():
        return FileResponse(_logo_md, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})
    raise AppError(ErrorCodes.NOT_FOUND, "Logo not found", 404)
