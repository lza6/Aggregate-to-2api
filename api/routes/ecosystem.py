"""TensorFeed AI 生态展示（v6.7.0）：聚合上游公开只读数据的只读端点。

上游（https://tensorfeed.ai，免费无 key）四个端点：
  GET /api/models           → {ok, lastUpdated, providers:[{id,name,models:[...]}]}
  GET /api/status/summary   → {ok, services:[{name,status,provider}]}
  GET /api/today            → {ok, generated_at, news/inference/papers/hf...}
  GET /api/health           → {ok, timestamp, news/models}

本模块并发拉取并归一化为统一结构，内存 LRU 缓存 + 防击穿锁。
上游失败时逐段容错（available=False），不整体失败；有旧缓存则 stale 回退。
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx
from fastapi import APIRouter

from .. import config
from ..cache import LRUCache
from ..errors import AppError, ErrorCodes

router = APIRouter()

log = logging.getLogger("imagefree_api")

TENSORFEED_BASE = config.IF_TENSORFEED_BASE
_CACHE_KEY = "ai-ecosystem"

# 惰性 LRU 缓存：maxsize=8、TTL=IF_TENSORFEED_CACHE_TTL（默认 900s）
_ecosystem_cache: LRUCache | None = None
# 防击穿锁：并发未命中时只允许一方拉上游
_fetch_lock = asyncio.Lock()
# 最近一次成功拉取的上游快照（仅在成功时覆盖；上游失败时用于 stale 回退）
_last_good: dict | None = None

# 共享 httpx.AsyncClient（参照 imagefree_client._get_client() 模式，timeout=20s + UA）
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """惰性创建共享 client：复用连接，避免每请求 TLS 握手。"""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            headers={"User-Agent": config.USER_AGENT},
        )
    return _client


async def close_client() -> None:
    """服务停止时关闭共享连接池（生命周期接入）."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_cache() -> LRUCache:
    """惰性初始化缓存实例。"""
    global _ecosystem_cache
    if _ecosystem_cache is None:
        _ecosystem_cache = LRUCache(maxsize=8, ttl=config.IF_TENSORFEED_CACHE_TTL)
    return _ecosystem_cache


# ── 上游抓取 + 归一化 ──────────────────────────────


async def _get(path: str) -> dict | None:
    """拉取单个端点；非 200 / 非 JSON / 传输异常 → None（容错，不抛）。"""
    try:
        r = await _get_client().get(TENSORFEED_BASE + path)
        if r.status_code != 200:
            log.warning("TensorFeed %s 非 200: %s", path, r.status_code)
            return None
        if not r.headers.get("content-type", "").startswith("application/json"):
            log.warning("TensorFeed %s 非 JSON 响应", path)
            return None
        payload = r.json()
        if not isinstance(payload, dict):
            log.warning("TensorFeed %s 响应不是对象", path)
            return None
        return payload
    except Exception as e:  # noqa: BLE001 - 上游异常统一容错降级
        log.warning("TensorFeed %s 请求异常: %s", path, e)
        return None


def _norm_models(raw: dict | None) -> dict:
    """/api/models → {available, last_updated, count, providers:[{id,name,models:[...]}]}"""
    if not raw or not raw.get("ok"):
        return {"available": False, "last_updated": None, "count": 0, "providers": []}
    providers: list[dict] = []
    models_expanded: list[dict] = []
    for p in raw.get("providers") or []:
        models = p.get("models") or []
        providers.append({
            "id": p.get("id", ""),
            "name": p.get("name", p.get("id", "")),
            "models": models,
        })
        models_expanded.extend(m["id"] for m in models if m.get("id"))
    return {
        "available": True,
        "last_updated": raw.get("lastUpdated"),
        "count": len(models_expanded),
        "providers": providers,
    }


def _norm_status(raw: dict | None) -> dict:
    """/api/status/summary → {available, all_operational, service_count, services, issues}"""
    if not raw or not raw.get("ok"):
        return {"available": False, "all_operational": False, "service_count": 0,
                "services": [], "issues": []}
    services: list[dict] = []
    issues: list[str] = []
    non_op = 0
    for s in raw.get("services") or []:
        name = s.get("name", "")
        status = s.get("status") or "unknown"
        services.append({"name": name, "status": status, "provider": s.get("provider")})
        if status not in ("operational", "ok", "up"):
            non_op += 1
            issues.append(f"{name}（{status}）")
    return {
        "available": True,
        "all_operational": non_op == 0,
        "service_count": len(services),
        "services": services,
        "issues": issues,
    }


def _norm_today(raw: dict | None) -> dict:
    """/api/today → {available, news(前3), inference, papers(前3), hf(前3)}"""
    if not raw or not raw.get("ok"):
        return {"available": False, "news": [], "inference": {}, "papers": [], "hf": []}
    news_raw = (raw.get("news") or {}).get("items") or []
    papers_raw = (raw.get("papers") or {}).get("ai_trending") or {}
    papers_items = papers_raw.get("papers") or []
    hf_items = (raw.get("hf") or {}).get("models") or {}
    hf_list = hf_items.get("items") if isinstance(hf_items, dict) else []
    return {
        "available": True,
        "generated_at": raw.get("generated_at"),
        "news": news_raw[:3],
        "inference": raw.get("inference") or {},
        "papers": papers_items[:3],
        "hf": hf_list[:3] if isinstance(hf_list, list) else [],
    }


def _norm_health(raw: dict | None) -> dict:
    """/api/health → {available, news_count, model_count}"""
    if not raw or not raw.get("ok"):
        return {"available": False, "news_count": None, "model_count": None}
    news = (raw.get("news") or {}).get("totalArticles")
    models = (raw.get("models") or {}).get("count")
    return {"available": True, "news_count": news, "model_count": models}


async def _fetch_upstream() -> dict:
    """并发拉 4 个端点 + 逐个容错归一化。"""
    models_raw, status_raw, today_raw, health_raw = await asyncio.gather(
        _get("/api/models"),
        _get("/api/status/summary"),
        _get("/api/today"),
        _get("/api/health"),
    )
    models = _norm_models(models_raw)
    status = _norm_status(status_raw)
    today = _norm_today(today_raw)
    health = _norm_health(health_raw)

    some_up = any(s["available"] for s in (models, status, today, health))
    if not some_up:
        raise AppError(
            ErrorCodes.UPSTREAM_ERROR,
            "TensorFeed 上游暂不可用，请稍后重试",
            status_code=502,
        )

    return {
        "models": models,
        "status": status,
        "today": today,
        "health": health,
        "cache": {
            "ttl_seconds": config.IF_TENSORFEED_CACHE_TTL,
            "fetched_from_upstream_at": int(time.time()),
        },
    }


# ── 路由 ─────────────────────────────────────────────


@router.get("/v1/ai-ecosystem")
async def ai_ecosystem() -> dict:
    """TensorFeed AI 生态面板（模型价格 / 服务状态 / 今日简报 / 健康）。"""
    cache = get_cache()
    cached = await cache.get(_CACHE_KEY)
    if cached is not None:
        return cached

    async with _fetch_lock:
        # double-check：锁内若已有人填充则直接返回，防击穿
        cached = await cache.get(_CACHE_KEY)
        if cached is not None:
            return cached

        global _last_good
        try:
            payload = await _fetch_upstream()
        except AppError:
            # 上游失败：有旧缓存则回退 stale，无缓存抛 502
            if _last_good is not None:
                return {** _last_good, "stale": True}
            raise

        _last_good = payload

        await cache.set(_CACHE_KEY, payload)
        return payload