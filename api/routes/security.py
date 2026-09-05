"""安全风控管理端点（ISSUE-02）。

提供动态封禁 / 解封 / 列表 / 统计。鉴权边界（ISSUE-02 加固）：
- 优先使用独立管理 Key 池 IF_ADMIN_KEYS；
- 未配置管理 Key 时继承业务 Key IF_API_KEYS（兼容降级）；
- 两者均未配置 → 默认拒绝管理操作，仅显式 IF_ADMIN_KEY_OPEN=1（本地运维/内网）时放行。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from .. import config
from ..auth import check_admin_key
from ..db.ip_blocklist_store import ip_blocklist_store
from ..errors import AppError, ErrorCodes
from ..request_guard import apply_ip_rule, invalidate_ip_cache

router = APIRouter()

log = logging.getLogger("imagefree_api.security")


def _require_admin_key(request: Request) -> None:
    """安全管理端点鉴权：独立管理 Key（未配置时继承业务 Key，两者皆空默认拒绝）。"""
    check_admin_key(request, scope="admin-security")


def _validate_ip(ip: str) -> str:
    """IP 基础格式校验（IPv4 / IPv6 字面量，严格校验）。"""
    ip = (ip or "").strip()
    if not ip:
        raise AppError(ErrorCodes.BAD_REQUEST, "ip 不能为空", 400)
    try:
        import ipaddress

        ipaddress.ip_address(ip)
    except ValueError:
        raise AppError(ErrorCodes.BAD_REQUEST, f"ip 格式非法: {ip}", 400)
    return ip


def _validate_block_type(block_type: str) -> str:
    bt = (block_type or "block").strip().lower()
    if bt not in ("block", "daily_limit"):
        raise AppError(ErrorCodes.BAD_REQUEST, "block_type 仅支持 block / daily_limit", 400)
    return bt


@router.post("/v1/admin/security/block-ip")
async def block_ip(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """动态封禁 IP。

    body 支持：
    - ip: 必填，IP 地址
    - block_type: 'block'（全量拦截）| 'daily_limit'（每日次数限制）
    - daily_limit: block_type='daily_limit' 时的每日最大次数（默认 1）
    - reason: 封禁原因
    - ttl_seconds: 有效时长（秒），0=永久
    """
    _require_admin_key(request)
    ip = _validate_ip(body.get("ip", ""))
    block_type = _validate_block_type(body.get("block_type", "block"))
    # daily_limit 仅对 block_type='daily_limit' 有意义；'block' 全量拦截时忽略该字段（不校验 >=1）
    if block_type == "daily_limit":
        try:
            daily_limit_raw = body.get("daily_limit", 1)
            daily_limit = int(daily_limit_raw) if daily_limit_raw not in (None, "") else 1
        except (TypeError, ValueError):
            raise AppError(ErrorCodes.BAD_REQUEST, "daily_limit 需为整数", 400)
        if daily_limit < 1:
            raise AppError(ErrorCodes.BAD_REQUEST, "daily_limit 需 >= 1", 400)
    else:
        daily_limit = 0
    reason = str(body.get("reason", "") or "")[:500]
    try:
        ttl_seconds = float(body.get("ttl_seconds", 0) or 0)
    except (TypeError, ValueError):
        raise AppError(ErrorCodes.BAD_REQUEST, "ttl_seconds 需为数字", 400)
    if ttl_seconds < 0:
        raise AppError(ErrorCodes.BAD_REQUEST, "ttl_seconds 需 >= 0", 400)

    rec = await ip_blocklist_store.add_or_update(
        ip=ip,
        block_type=block_type,
        daily_limit=daily_limit,
        reason=reason,
        ttl_seconds=ttl_seconds,
    )
    # 立即写入内存缓存，下一次请求即生效（不依赖全量同步空窗）
    apply_ip_rule(ip, rec)
    log.warning(
        "安全风控: 动态封禁 %s (type=%s, limit=%s, ttl=%ss, reason=%s)",
        ip,
        block_type,
        daily_limit,
        ttl_seconds,
        reason,
    )
    return {"ok": True, "record": rec}


@router.delete("/v1/admin/security/unblock-ip")
async def unblock_ip(request: Request, ip: str = "") -> dict[str, Any]:
    """解封 IP。"""
    _require_admin_key(request)
    ip = _validate_ip(ip)
    removed = await ip_blocklist_store.remove(ip)
    invalidate_ip_cache(ip)
    if not removed:
        return {"ok": True, "removed": False, "note": "该 IP 不在封禁表中"}
    log.warning("安全风控: 解封 %s", ip)
    return {"ok": True, "removed": True}


@router.get("/v1/admin/security/blocklist")
async def blocklist(
    request: Request,
    page: int = 1,
    page_size: int = 100,
    since_ts: float | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """列出当前生效封禁规则（P2-2 分页）。

    向后兼容旧 limit 参数：传 limit 时走旧单参数语义（page 忽略，limit 钳到 [1,10000]）。
    新参数：
    - page: 页码（从 1 开始，默认 1）
    - page_size: 每页条数（默认 100，上限 1000）
    - since_ts: 时间游标（仅返回 updated_at >= since_ts 的记录）
    返回信封 {items, total, page, page_size, has_more}。
    """
    _require_admin_key(request)
    page = max(1, page)
    page_size = max(1, min(page_size, 1000))
    # 旧 limit 兼容：显式传 limit 时走旧语义（offset=0，page 参数被忽略）
    if limit is not None:
        page_size = max(1, min(int(limit), 1000))
        page = 1
    offset = (page - 1) * page_size
    items = await ip_blocklist_store.list_all(limit=page_size, offset=offset, since_ts=since_ts)
    total = await ip_blocklist_store.count(since_ts=since_ts)
    has_more = (offset + len(items)) < total
    return {
        "items": items,
        "count": len(items),
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": has_more,
    }


@router.get("/v1/admin/security/status")
async def block_status(request: Request, ip: str = "") -> dict[str, Any]:
    """查询单个 IP 的当前生效规则（不存在或已过期返回 None）。

    v7.7.4: 附带 admin_contact（管理员申诉联系方式），供被封禁用户联系解封。
    """
    _require_admin_key(request)
    ip = _validate_ip(ip)
    rule = await ip_blocklist_store.get(ip)
    return {
        "ip": ip,
        "rule": rule,
        "blocked": rule is not None,
        "admin_contact": getattr(config, "IF_ADMIN_CONTACT", "") or "",
    }


@router.get("/v1/admin/security/stats")
async def security_stats(request: Request) -> dict[str, Any]:
    """风控统计：封禁总数 + 当前活跃每日限制数（P2-2 用 count 替代全量加载）。

    P2-2：原先 list_all(limit=10000) 全量加载做统计 → 改用 count() + 分批累加，
    避免封禁表膨胀时 OOM。block/daily_limit 计数仍取第一页样本（总数已由 count 给出）。
    """
    _require_admin_key(request)
    total = await ip_blocklist_store.count()
    # P3-(v7.3): 用 GROUP BY 精确聚合分布，替代 list_all(1000) 样本估算
    #（>1000 条时样本会失真——原 v6.9.1 的 list_all(10000) 精确统计被 P2-2 降级为近似）。
    by_type = await ip_blocklist_store.count_by_type()
    blocks = by_type.get("block", 0)
    daily = by_type.get("daily_limit", 0)
    return {"total": total, "block": blocks, "daily_limit": daily}
