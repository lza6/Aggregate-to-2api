"""画廊相似图检索路由（P3-D1）：GET /v1/gallery/similar。

依赖：
- ``IF_VECTOR_SEARCH_ENABLED=1`` 启用向量检索（缺省关闭，渐进启用）
- sqlite-vec 可用时走 KNN；不可用时降级纯 Python 线性扫描

端点：
- ``GET /v1/gallery/similar?task_id=xxx&top_k=10``：返回相似图 top-K
- ``GET /v1/gallery/similar/stats``：向量存储统计（管理端可见，无鉴权）
- ``GET /v1/gallery/duplicates?limit=50``：列出被标记为重复的任务
- v16 P0-3 画廊管理端：
  - ``GET /v1/gallery``：分页列表（page/page_size/status/model/search）——**权威实现在
    api/routes/admin/query.py**（含 limit 兼容 + count/total 双字段 + gallery:{limit} 缓存），本模块不重复定义
  - ``GET /v1/gallery/search?q=``：prompt 子串搜索（复用列表 search 参数）
  - ``GET /v1/gallery/{task_id}``：单张详情（含 similar 推荐 top_k）
  - ``POST /v1/gallery/zip``：多 task_id 服务端打包 ZIP（StreamingResponse，临时文件流式，分批）
  - ``DELETE /v1/gallery/{task_id}``：软删（status→deleted，可回滚）

鉴权：复用画廊鉴权链（签名 URL / 静态密码 / 开放），与 /v1/gallery 一致。
"""

from __future__ import annotations

import logging
import os
import tempfile
import zipfile
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import check_admin_key
from ..errors import AppError, ErrorCodes

log = logging.getLogger("imagefree_api.gallery_similar")

# 独立 router（不挂 admin 包的 _common，本路由文件在 api/routes/ 下而非 admin/ 子包）
router = APIRouter()

# v16 P0-3：ZIP 打包单批上限（防 512MB 容器 OOM；超出分批打包）
_DEFAULT_ZIP_BATCH = 20


def _gallery_zip_batch() -> int:
    """打包单批上限（IF_GALLERY_ZIP_BATCH，缺省 20；走 config 工厂）。"""
    try:
        from ..config import get_settings

        return max(1, int(getattr(get_settings(), "if_gallery_zip_batch", _DEFAULT_ZIP_BATCH)))
    except Exception:
        return _DEFAULT_ZIP_BATCH


def _gallery_page_size() -> int:
    """画廊分页大小（IF_GALLERY_PAGE_SIZE，默认 50，上限 200；走 config 工厂）。"""
    try:
        from ..config import get_settings

        v = int(getattr(get_settings(), "if_gallery_page_size", 50))
    except Exception:
        v = 50
    return min(max(1, v), 200)


def _gallery_auth(password: str | None) -> None:
    """复用 admin.query 的画廊鉴权链（签名 URL / 静态密码 / 开放）。"""
    from .admin.query import _gallery_auth as _auth

    _auth(password)


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
    _gallery_auth(password)

    from ..vector.store import get_vector_store

    items = await get_vector_store().list_duplicates(limit=limit)
    return {
        "items": items,
        "count": len(items),
        "threshold": _dedupe_threshold(),
    }


# ── v16 P0-3 画廊管理端：列表/搜索/详情/打包/软删 ──────────────

# 注：GET /v1/gallery（分页列表）为 admin/query.py 的权威实现（含 limit 兼容 + gallery:{limit}
# 缓存 + count/total 双字段）；本模块仅保留 search/detail/zip/delete 与相似检索——避免同路径双路由。


def _db() -> Any:
    """取 DB 实例（meta 单例，与 tasks.py 同源）。"""
    from ..meta import db

    return db


@router.get("/v1/gallery/search", include_in_schema=False)
async def gallery_search(
    q: str = Query(..., min_length=1, max_length=200, description="prompt 子串"),
    page: int = Query(1, ge=1),
    page_size: int | None = Query(None, ge=1, le=200),
    password: str | None = Query(None, description="画廊访问密码/签名 token"),
) -> dict:
    """画廊搜索（prompt 子串/模型过滤），复用列表 search 参数。"""
    _gallery_auth(password)
    items, total = await _db().gallery_list(
        page=page,
        page_size=page_size or _gallery_page_size(),
        search=q,
    )
    return {"items": items, "total": total, "query": q}


@router.get("/v1/gallery/{task_id}", include_in_schema=False)
async def gallery_detail(
    task_id: str,
    password: str | None = Query(None, description="画廊访问密码/签名 token"),
    top_k: int = Query(5, ge=0, le=20, description="相似推荐数量（0=不返回）"),
) -> dict:
    """画廊单张详情（含相似推荐 top_k，向量未启用时推荐为空列表不报错）。"""
    _gallery_auth(password)
    item = await _db().gallery_get(task_id)
    if item is None:
        raise AppError(ErrorCodes.NOT_FOUND, f"画廊无此图片：{task_id}", 404)
    similar: list[dict[str, Any]] = []
    if top_k > 0 and _vector_enabled():
        try:
            from ..vector.store import get_vector_store

            raw_similar = await get_vector_store().similar_search(task_id, top_k=top_k)
            # H3 修复（审查）：similar_search 只返回 {task_id, similarity,...}，缺前端渲染所需字段
            # （id/image_url/prompt）→ 反查 requests 表补齐；缺失/已软删的条目跳过。
            for sim in raw_similar:
                sim_id = sim.get("task_id") or sim.get("id")
                if not sim_id:
                    continue
                detail_row = await _db().gallery_get(str(sim_id))
                if detail_row is None:
                    continue
                enriched = {"id": str(sim_id), "similarity": sim.get("similarity")}
                enriched.update(detail_row)
                similar.append(enriched)
        except Exception as exc:  # noqa: BLE001 — 推荐是增强，失败降级空列表
            log.warning("画廊相似推荐降级 task_id=%s: %s", task_id, exc)
    return {"item": item, "similar": similar, "similar_count": len(similar)}


class _ZipRequest(BaseModel):
    """画廊打包请求体（v16 P0-3）：{task_ids: [str, ...]}。"""

    task_ids: list[str] = []


@router.post("/v1/gallery/zip", include_in_schema=False)
async def gallery_zip(
    payload: _ZipRequest,
    password: str | None = Query(None, description="画廊访问密码/签名 token"),
) -> StreamingResponse:
    """画廊批量打包 ZIP（v16 P0-3）。

    - 请求体：{task_ids: [str, ...]}（上限 IF_GALLERY_ZIP_BATCH=20，超出分批）
    - 实现：先写临时文件（流式写入）→ StreamingResponse 流式下发 → 完成后清理
      （避开 512MB 容器全量内存 zipfile OOM 风险）
    - 失败张跳过并回报清单（response header X-Skipped）
    """
    _gallery_auth(password)
    task_ids = payload.task_ids
    if not task_ids:
        raise AppError(ErrorCodes.BAD_REQUEST, "task_ids 不能为空", 400)
    # 分批上限：避免单请求拉爆（多批时只打包本批，前端可分页打包）
    batch = task_ids[: _gallery_zip_batch()]

    # 预取条目（过滤软删/不存在）+ 显式读 base64 内容（列表不投影 base64，防分页 OOM）
    items: list[dict[str, Any]] = []
    skipped: list[str] = []
    for tid in batch:
        item = await _db().gallery_get(str(tid))
        if item is None:
            skipped.append(str(tid))
        else:
            item["image_base64"] = await _db().read_base64(str(tid))
            items.append(item)

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
            tmp_path = tf.name
        import asyncio

        loop = asyncio.get_running_loop()

        def _build() -> None:
            """同步构建 ZIP（放线程池避免阻塞事件循环；图片用 base64 内嵌——不物理读文件）。"""
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for item in items:
                    b64 = item.get("image_base64") or ""
                    if not b64:
                        continue
                    # LOW（审查）：mime.split('/')[-1] 会把 svg+xml 切坏 → 复用 base64_store 的映射
                    from ..base64_store import _mime_to_ext

                    ext = _mime_to_ext(item.get("image_mime") or "image/png")
                    fname = f"{item['id']}.{ext or 'png'}"
                    try:
                        import base64 as _b64

                        # production 落库的是 data URI（data:image/png;base64,...），剥前缀再解
                        raw_b64 = b64.split(",", 1)[-1] if b64.startswith("data:") else b64
                        raw = _b64.b64decode(raw_b64)
                        zf.writestr(fname, raw)
                    except Exception as exc:  # noqa: BLE001 — 单张失败跳过
                        skipped.append(str(item.get("id")))
                        log.warning("画廊打包跳过 task_id=%s: %s", item.get("id"), exc)

        await loop.run_in_executor(None, _build)

        def _iter_file():
            try:
                with open(tmp_path, "rb") as f:
                    yield from f
            finally:
                if tmp_path:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

        headers = {
            "Content-Disposition": 'attachment; filename="gallery.zip"',
            "X-Skipped": ",".join(skipped),
            "X-Total": str(len(items)),
        }
        return StreamingResponse(_iter_file(), media_type="application/zip", headers=headers)
    except Exception:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


@router.delete("/v1/gallery/{task_id}", include_in_schema=False)
async def gallery_delete(
    task_id: str,
    request: Request,
    password: str | None = Query(None, description="画廊访问密码/签名 token"),
) -> dict:
    """画廊软删（v16 P0-3）：status → 'deleted'，不物理删文件，可回滚。

    鉴权：H4 修复（审查）——写操作（删库）叠加管理 Key（IF_ADMIN_KEYS / 开放模式放行），
    仅凭画廊展示密码/签名不得删作品（读组≠写组）。
    """
    _gallery_auth(password)
    check_admin_key(request, scope="gallery-delete")
    ok = await _db().gallery_soft_delete(task_id)
    if not ok:
        raise AppError(ErrorCodes.NOT_FOUND, f"画廊无此图片：{task_id}", 404)
    # M2 修复（审查）：软删后失效 gallery:{limit} 缓存，避免 TTL 窗口内旧列表仍显示已删条目
    try:
        from ..meta import gallery_cache

        await gallery_cache.invalidate_prefix("gallery:")
    except Exception as exc:  # noqa: BLE001 — 缓存失效失败不阻断删除
        log.warning("画廊软删缓存失效失败 task_id=%s: %s", task_id, exc)
    return {"deleted": True, "task_id": task_id, "soft": True}


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
    "gallery_search",
    "gallery_detail",
    "gallery_zip",
    "gallery_delete",
    "on_task_completed",
]
