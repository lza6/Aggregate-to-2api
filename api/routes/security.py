"""安全风控管理端点（ISSUE-02）。

提供动态封禁 / 解封 / 列表 / 统计。鉴权边界（ISSUE-02 加固）：
- 优先使用独立管理 Key 池 IF_ADMIN_KEYS；
- 未配置管理 Key 时继承业务 Key IF_API_KEYS（兼容降级）；
- 两者均未配置 → 默认拒绝管理操作，仅显式 IF_ADMIN_KEY_OPEN=1（本地运维/内网）时放行。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

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
async def block_ip(request: Request, body: dict):
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
    try:
        daily_limit_raw = body.get("daily_limit", 1)
        daily_limit = int(daily_limit_raw) if daily_limit_raw not in (None, "") else 1
    except (TypeError, ValueError):
        raise AppError(ErrorCodes.BAD_REQUEST, "daily_limit 需为整数", 400)
    if daily_limit < 1:
        raise AppError(ErrorCodes.BAD_REQUEST, "daily_limit 需 >= 1", 400)
    reason = str(body.get("reason", "") or "")[:500]
    try:
        ttl_seconds = float(body.get("ttl_seconds", 0) or 0)
    except (TypeError, ValueError):
        raise AppError(ErrorCodes.BAD_REQUEST, "ttl_seconds 需为数字", 400)
    if ttl_seconds < 0:
        raise AppError(ErrorCodes.BAD_REQUEST, "ttl_seconds 需 >= 0", 400)

    rec = await ip_blocklist_store.add_or_update(
        ip=ip, block_type=block_type, daily_limit=daily_limit,
        reason=reason, ttl_seconds=ttl_seconds,
    )
    # 立即写入内存缓存，下一次请求即生效（不依赖全量同步空窗）
    apply_ip_rule(ip, rec)
    log.warning("安全风控: 动态封禁 %s (type=%s, limit=%s, ttl=%ss, reason=%s)",
                ip, block_type, daily_limit, ttl_seconds, reason)
    return {"ok": True, "record": rec}


@router.delete("/v1/admin/security/unblock-ip")
async def unblock_ip(request: Request, ip: str = ""):
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
async def blocklist(request: Request, limit: int = 200):
    """列出当前生效封禁规则。"""
    _require_admin_key(request)
    rules = await ip_blocklist_store.list_all(limit=max(1, min(limit, 1000)))
    return {"items": rules, "count": len(rules)}


@router.get("/v1/admin/security/status")
async def block_status(request: Request, ip: str = ""):
    """查询单个 IP 的当前生效规则（不存在或已过期返回 None）。"""
    _require_admin_key(request)
    ip = _validate_ip(ip)
    rule = await ip_blocklist_store.get(ip)
    return {"ip": ip, "rule": rule, "blocked": rule is not None}


@router.get("/v1/admin/security/stats")
async def security_stats(request: Request):
    """风控统计：封禁总数 + 当前活跃每日限制数。"""
    _require_admin_key(request)
    rules = await ip_blocklist_store.list_all(limit=10000)
    blocks = sum(1 for r in rules if r.get("block_type") == "block")
    daily = sum(1 for r in rules if r.get("block_type") == "daily_limit")
    return {"total": len(rules), "block": blocks, "daily_limit": daily}