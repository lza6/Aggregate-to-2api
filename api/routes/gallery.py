"""画廊相似图检索路由（P3-D1）：GET /v1/gallery/similar。

依赖：
- ``IF_VECTOR_SEARCH_ENABLED=1`` 启用向量检索（缺省关闭，渐进启用）
- sqlite-vec 可用时走 KNN；不可用时降级纯 Python 线性扫描

端点：
- ``GET /v1/gallery/similar?task_id=xxx&top_k=10``：返回相似图 top-K
- ``GET /v1/gallery/similar/stats``：向量存储统计（管理端可见，无鉴权）
- ``GET /v1/gallery/duplicates?limit=50``：列出被标记为重复的任务

鉴权：复用画廊鉴权链（签名 URL / 静态密码 / 开放），与 /v1/gallery 一致。
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Query

from ..errors import AppError, ErrorCodes

log = logging.getLogger("imagefree_api.gallery_similar")

# 独立 router（不挂 admin 包的 _common，本路由文件在 api/routes/ 下而非 admin/ 子包）
router = APIRouter()


def _dedupe_threshold() -> float:
    """查重相似度阈值（IF_VECTOR_DEDUPE_THRESHOLD，默认 0.95）。"""
    raw = os.getenv("IF_VECTOR_DEDUPE_THRESHOLD", "0.95")
    try:
        v = float(raw)
        return v if 0.0 < v <= 1.0 else 0.95
    except (TypeError, ValueError):
        return 0.95


def _vector_enabled() -> bool:
    """向量检索开关（IF_VECTOR_SEARCH_ENABLED，缺省 0=关闭）。"""
    val = os.getenv("IF_VECTOR_SEARCH_ENABLED", "0")
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _require_vector_enabled() -> None:
    """向量检索未启用时返回 503，提示管理员开启。"""
    if not _vector_enabled():
        raise AppError(
            ErrorCodes.PROVIDER_DOWN,
            "向量检索未启用（设置 IF_VECTOR_SEARCH_ENABLED=1 开启）",
            503,
        )


# ── /v1/gallery/similar ──────────────────────────────────


@router.get("/v1/gallery/similar")
async def gallery_similar(
    task_id: str = Query(..., description="锚点任务 ID"),
    top_k: int = Query(10, ge=1, le=50, description="返回相似图数量上限"),
    password: str | None = Query(None, description="画廊访问密码/签名 token"),
) -> dict:
    """返回与指定任务最相似的 top_k 个任务（基于 prompt embedding）。

    鉴权同 /v1/gallery：签名 URL 优先，回退静态密码，皆空开放。
    """
    _require_vector_enabled()
    # 复用画廊鉴权（不重复实现）
    from .admin.query import _gallery_auth  # type: ignore[attr-defined]

    _gallery_auth(password)

    from ..vector.store import get_vector_store

    store = get_vector_store()
    items = await store.similar_search(task_id, top_k=top_k)
    return {
        "task_id": task_id,
        "items": items,
        "count": len(items),
        "top_k": top_k,
    }


@router.get("/v1/gallery/similar/stats", include_in_schema=False)
async def gallery_similar_stats() -> dict:
    """向量存储统计（无鉴权，只读聚合数据；管理端可见）。

    未启用时返回 ``{"enabled": false}``，不报错（便于前端优雅降级）。
    """
    if not _vector_enabled():
        return {"enabled": False, "total": 0, "duplicates": 0, "backend": "disabled"}
    from ..vector.store import get_vector_store

    return await get_vector_store().stats()


@router.get("/v1/gallery/duplicates", include_in_schema=False)
async def gallery_duplicates(
    limit: int = Query(50, ge=1, le=200, description="返回数量上限"),
    password: str | None = Query(None, description="画廊访问密码/签名 token"),
) -> dict:
    """列出被标记为重复的任务（入库时相似度 > 阈值）。

    鉴权同 /v1/gallery。
    """
    _require_vector_enabled()
    from .admin.query import _gallery_auth  # type: ignore[attr-defined]

    _gallery_auth(password)

    from ..vector.store import get_vector_store

    items = await get_vector_store().list_duplicates(limit=limit)
    return {
        "items": items,
        "count": len(items),
        "threshold": _dedupe_threshold(),
    }


# ── 入库钩子（供 dispatch.py 在 mark_finished 后调用）──


async def on_task_completed(task_id: str, prompt: str) -> None:
    """任务完成时的向量入库钩子（dispatch.py 调用）。

    - 向量检索未启用时短路返回（零开销）
    - 启用时计算 embedding + 查重 + 标记 is_duplicate
    - 异常不抛（向量检索是旁路，不影响主链路）

    在 dispatch.py mark_finished("completed", ...) 之后调用：
        from api.routes.gallery import on_task_completed
        await on_task_completed(task_id, prompt)
    """
    if not _vector_enabled():
        return
    try:
        from ..vector.store import get_vector_store

        store = get_vector_store()
        await store.upsert(
            task_id,
            prompt,
            check_duplicate=True,
            duplicate_threshold=_dedupe_threshold(),
        )
    except Exception as e:
        log.warning("向量入库失败 task_id=%s: %s", task_id, e)


__all__ = [
    "gallery_similar",
    "gallery_similar_stats",
    "gallery_duplicates",
    "on_task_completed",
]
