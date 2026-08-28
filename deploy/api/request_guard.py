"""公开生成接口的轻量请求限速与动态风控（ISSUE-01/ISSUE-02 改造）。

特性：
- 采用 StorageAdapter 统一驱动限流（单机 MemoryRateLimiter 或集群 RedisRateLimiter）。
- 结合 SQLite `ip_blocklist` 与内存高速缓存实现毫秒级动态封禁、每日限流拦截与风控。
- 移除硬编码 IP，支持管理面动态添加/移除/TTL过期自动清理。
- 支持 IP 白名单（IF_IP_WHITELIST）与频繁超限自动入黑名单（IF_AUTO_BLOCK_*）。
- 识别真实客户端 IP：优先 X-Forwarded-For 首段（Nginx/Caddy 反代）。
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from typing import Optional

from fastapi import Request

from . import config
from .errors import AppError, ErrorCodes
from .db.ip_blocklist_store import ip_blocklist_store

log = logging.getLogger("request_guard")

_lock = threading.Lock()
_WINDOW_SECONDS = 60.0
_DEFAULT_REQUESTS_PER_MINUTE = 10
_DAY_SECONDS = 86400.0

# 内存高速缓存：避免每次请求都读取 DB
# ip -> {"block_type": str, "daily_limit": int, "expire_at": float, "reason": str, ...}
_BLOCKLIST_CACHE: dict[str, dict] = {}
_BLOCKLIST_CACHE_TTL = 30.0  # 30 秒全量同步一次
_LAST_CACHE_SYNC: float = 0.0

# 每日调用历史追踪: ip -> list[float]（block_type='daily_limit' 时计数）
_ip_daily_records: dict[str, list[float]] = {}
# 频控超限逾期记录（自动入黑名单依据）: ip -> deque[float]（monotonic 时间戳）
_rate_violations: dict[str, deque[float]] = {}


def _whitelist_ips() -> set[str]:
    """白名单 IP 集合（策略级绕过封禁与限速）。"""
    raw = getattr(config, "IF_IP_WHITELIST", "") or ""
    if isinstance(raw, str):
        return {p.strip() for p in raw.split(",") if p.strip()}
    return set(raw or [])


def _auto_block_enabled() -> bool:
    return bool(getattr(config, "IF_AUTO_BLOCK_ENABLED", True))


def _auto_block_threshold() -> int:
    try:
        return max(1, int(getattr(config, "IF_AUTO_BLOCK_THRESHOLD", 3)))
    except (TypeError, ValueError):
        return 3


def _auto_block_window() -> float:
    try:
        return float(max(1, int(getattr(config, "IF_AUTO_BLOCK_WINDOW_SECONDS", 300))))
    except (TypeError, ValueError):
        return 300.0


def _auto_block_ttl() -> float:
    try:
        return float(max(0, int(getattr(config, "IF_AUTO_BLOCK_TTL_SECONDS", 3600))))
    except (TypeError, ValueError):
        return 3600.0


def _limit() -> int:
    """每分钟每 IP 允许的提交次数；默认 10 次/分钟。"""
    val = getattr(config, "IF_REQUESTS_PER_MINUTE", None)
    if val is not None and str(val).strip() != "":
        try:
            return int(val)
        except ValueError:
            pass
    return _DEFAULT_REQUESTS_PER_MINUTE


def _client_ip(request: Request) -> str:
    """在反代之后仍能拿到真实客户端 IP。"""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        first = xff.split(",", 1)[0].strip()
        if first and not first.lower().startswith(("127.", "10.", "192.168.", "::1", "unknown")):
            return first
    client = request.client
    return client.host if client else "unknown"


def invalidate_ip_cache(ip: Optional[str] = None) -> None:
    """清除 IP 封禁内存缓存（管理端修改后调用）。"""
    global _LAST_CACHE_SYNC
    with _lock:
        if ip:
            _BLOCKLIST_CACHE.pop(ip, None)
        else:
            _BLOCKLIST_CACHE.clear()
        _LAST_CACHE_SYNC = 0.0


def apply_ip_rule(ip: str, rule: Optional[dict]) -> None:
    """把一条规则立即写入内存高速缓存（封禁毫秒级生效；rule=None 表示移除）。

    管理端「封禁/解封」后调用，避免依赖下一次全量同步造成空窗期。
    """
    with _lock:
        if rule is None:
            _BLOCKLIST_CACHE.pop(ip, None)
        else:
            _BLOCKLIST_CACHE[ip] = rule


def reset_runtime_state() -> None:
    """清空全部内存级缓存与计数（管理端运维 / 测试隔离用）。"""
    global _LAST_CACHE_SYNC
    with _lock:
        _BLOCKLIST_CACHE.clear()
        _ip_daily_records.clear()
        _rate_violations.clear()
        _LAST_CACHE_SYNC = 0.0


def _get_cached_ip_rule(ip: str) -> Optional[dict]:
    """从内存缓存获取 IP 封禁规则；缓存过期条目自动剔除，未命中触发异步全量同步。"""
    global _LAST_CACHE_SYNC
    now = time.time()

    # 1. 尝试直接命中缓存
    with _lock:
        rule = _BLOCKLIST_CACHE.get(ip)
        if rule:
            expire_at = rule.get("expire_at", 0)
            if expire_at > 0 and expire_at < now:
                _BLOCKLIST_CACHE.pop(ip, None)
                return None
            return rule

    # 2. 定期全量同步缓存（异步触发，避免每次请求都读 DB）
    if now - _LAST_CACHE_SYNC > _BLOCKLIST_CACHE_TTL:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_sync_blocklist_cache())
        except RuntimeError:
            pass
        # 锁外更新节流戳（非精确，仅用于抖动静默降级）
        _LAST_CACHE_SYNC = now

    return None


async def _sync_blocklist_cache() -> None:
    """后台同步 DB 封禁表到内存缓存，并顺手清理过期记录。"""
    global _LAST_CACHE_SYNC
    try:
        rules = await ip_blocklist_store.list_all(limit=2000)
        now = time.time()
        new_cache = {r["ip"]: r for r in rules}
        with _lock:
            _BLOCKLIST_CACHE.clear()
            _BLOCKLIST_CACHE.update(new_cache)
            _LAST_CACHE_SYNC = now
        # 过期记录自动清理（禁入下轮全量查询）
        try:
            removed = await ip_blocklist_store.cleanup_expired()
            if removed:
                log.info("IP 封禁表过期记录清理: 删除 %d 条", removed)
        except Exception as e:
            log.warning("IP 封禁表过期清理失败: %s", e)
    except Exception as e:
        log.warning("同步 IP 封禁表缓存失败: %s", e)


async def sync_blocklist_cache() -> None:
    """公开入口：主动同步一次封禁缓存（应用启动/运维热载用）。"""
    await _sync_blocklist_cache()


def _record_auto_block_violation(ip: str, reason: str) -> None:
    """记录一次频控超限；在窗口内达到阈值后自动写入黑名单（异步）。"""
    if not _auto_block_enabled():
        return
    now = time.monotonic()
    window = _auto_block_window()
    trigger = False
    with _lock:
        bucket = _rate_violations.setdefault(ip, deque())
        while bucket and now - bucket[0] >= window:
            bucket.popleft()
        bucket.append(now)
        if len(bucket) >= _auto_block_threshold():
            # 达到阈值 → 清除计数，避免重复触发
            _rate_violations.pop(ip, None)
            trigger = True
    if trigger:
        log.warning("IP %s 频繁超限（窗口内 %d 次），触发自动入黑名单", ip, _auto_block_threshold())
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_auto_block_ip(ip, reason))
        except RuntimeError:
            pass  # 无事件循环时降级：仅限流，不自动封禁


async def _auto_block_ip(ip: str, reason: str) -> None:
    """把频繁超限 IP 写入封禁表并立即生效。"""
    try:
        rec = await ip_blocklist_store.add_or_update(
            ip=ip, block_type="block", reason=reason, ttl_seconds=_auto_block_ttl(),
        )
        apply_ip_rule(ip, rec)
        log.warning("安全风控: 自动封禁 %s (TTL=%ss, reason=%s)", ip, _auto_block_ttl(), reason)
    except Exception as e:
        log.warning("自动封禁 %s 失败: %s", ip, e)


def check_rate_limit(request: Request) -> None:
    """同步限速入口：执行动态风控（封禁/每日限额/白名单）与基础滑窗限速。"""
    key = _client_ip(request)
    now_ts = time.time()
    now_mono = time.monotonic()

    # 0. 白名单：直接放行（不封禁、不限流）
    if key in _whitelist_ips():
        return

    # 1. 动态 IP 封禁与风控规则检查
    rule = _get_cached_ip_rule(key)
    if rule:
        b_type = rule.get("block_type", "block")
        reason = rule.get("reason") or "安全风控限制"
        if b_type == "block":
            raise AppError(ErrorCodes.FORBIDDEN, f"该 IP 已被系统安全风控封禁: {reason}", 403)
        if b_type == "daily_limit":
            daily_limit = int(rule.get("daily_limit", 1))
            with _lock:
                records = _ip_daily_records.setdefault(key, [])
                records[:] = [t for t in records if now_ts - t < _DAY_SECONDS]
                if len(records) >= daily_limit:
                    raise AppError(
                        ErrorCodes.FORBIDDEN,
                        f"该 IP 触发安全风控，已被系统限制为每天最多 {daily_limit} 次调用",
                        403,
                    )
                records.append(now_ts)

    # 2. 基础滑动窗口限流检查（内存快速路径；0 = 关闭）
    limit = _limit()
    if limit <= 0:
        return

    limited = False
    with _lock:
        records = _ip_daily_records.setdefault(f"rate:{key}", [])
        records[:] = [t for t in records if now_mono - t < _WINDOW_SECONDS]
        if len(records) >= limit:
            limited = True
        else:
            records.append(now_mono)
        if len(_ip_daily_records) > 10000:
            expired = [k for k, v in _ip_daily_records.items()
                       if not v or now_mono - v[-1] >= _WINDOW_SECONDS]
            for k in expired:
                _ip_daily_records.pop(k, None)

    if limited:
        # 频繁超限自动入黑名单（在锁外触发，避免死锁）
        _record_auto_block_violation(key, f"每分钟超过 {limit} 次")
        raise AppError(ErrorCodes.RATE_LIMITED, f"请求过于频繁（>{limit}/分钟），请稍后重试", 429)


def check_generate_request(request: Request, prompt: str = "") -> None:
    """入口限速；prompt 参数保留以兼容调用方。"""
    del prompt
    check_rate_limit(request)