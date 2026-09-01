"""公开生成接口的轻量请求限速与动态风控（ISSUE-02，安全加固版）。

特性：
- 基于 SQLite `ip_blocklist` + 内存高速缓存实现毫秒级动态封禁、每日限流、TTL 过期清理。
- 管理面可动态封禁/解封（独立管理 Key，见 api/routes/security.py）。
- 移除硬编码 IP；支持白名单（IF_IP_WHITELIST）与频繁超限自动入黑名单（IF_AUTO_BLOCK_*）。
- 安全加固（B1 修复）：X-Forwarded-For 仅在「对端为受信代理」时才被解析，且取**最右**段
  （追加语义下最后一段由代理以 socket 对端追加，无法伪造）；对端非受信代理时一律以 socket
  对端为准，杜绝伪造 XFF 绕过封禁/限流/白名单或把第三方 IP 打黑。
- 安全加固（S1 修复）：daily_limit / 滑窗桶统一使用墙上时钟，避免异构时间戳导致桶永不清理。
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time

from fastapi import Request

from . import config
from .db.ip_blocklist_store import ip_blocklist_store
from .errors import AppError, ErrorCodes

log = logging.getLogger("request_guard")

# 保留 threading.Lock（非 asyncio.Lock）：临界区为纯内存 dict/deque 操作（微秒级），
# asyncio 单线程事件循环无竞争零阻塞；且 check_rate_limit 被同步调用链（routes/generate.
# _prepare→check_generate_request→check_rate_limit）使用，换 asyncio.Lock 会传染成 async。
# async 路径阻塞源是 ip_blocklist_store.list_all 的 sqlite3 I/O（见 _sync_blocklist_cache），
# 该 I/O 已 await，非此锁。真正的 P1 是同步 sqlite3 混入 async（account_pool/email_pool）。
_lock = threading.Lock()
_WINDOW_SECONDS = 60.0
_DEFAULT_REQUESTS_PER_MINUTE = 10
_DAY_SECONDS = 86400.0

# 常见私网/保留前缀：XFF 段命中这些视为「不可信源」，不作为最终客户端身份
_PRIVATE_PREFIX_HINTS = (
    "127.",
    "10.",
    "192.168.",
    "169.254.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "::1",
    "fe80:",
    "fc00:",
    "fd",
    "unknown",
)

# 内存高速缓存：避免每次请求都读取 DB
_BLOCKLIST_CACHE: dict[str, dict] = {}
_BLOCKLIST_CACHE_TTL = 30.0  # 30 秒全量同步一次
_LAST_CACHE_SYNC: float = 0.0

# 每日调用历史 / 滑窗计数枪：统一以墙上时钟（time.time()）为时间基
_ip_daily_records: dict[str, list[float]] = {}
# 频控超限逾期记录（自动入黑名单依据）: ip -> list[float]（墙上时钟）
_rate_violations: dict[str, list[float]] = {}
# L1 秒级令牌桶：ip -> [tokens, last_refill_ts]（墙上时钟）。tokens 浮点，回填按墙上时间差。
_l1_token_buckets: dict[str, list[float]] = {}


# ── 配置读取（默认值兼顾安全与部署兼容）──────────────────
def _whitelist_ips() -> set[str]:
    raw = getattr(config, "IF_IP_WHITELIST", "") or ""
    if isinstance(raw, str):
        return {p.strip() for p in raw.split(",") if p.strip()}
    return set(raw or [])


def _trusted_proxies() -> list[str]:
    """受信代理 IP 列表。默认信任本机反代（127.0.0.1 / ::1）。

    IF_TRUSTED_PROXIES 逗号分隔。当对端命中该列表时才解析 X-Forwarded-For；
    否则一律使用 socket 对端（不解析该头，从根上杜绝伪造）。
    """
    raw = getattr(config, "IF_TRUSTED_PROXIES", None)
    if raw is None or raw == "":
        return ["127.0.0.1", "::1"]
    if isinstance(raw, (list, tuple)):
        return [str(p).strip() for p in raw if str(p).strip()]
    return [p.strip() for p in str(raw).split(",") if p.strip()]


def _auto_block_enabled() -> bool:
    return bool(getattr(config, "IF_AUTO_BLOCK_ENABLED", True))


def _auto_block_threshold() -> int:
    try:
        return max(2, int(getattr(config, "IF_AUTO_BLOCK_THRESHOLD", 5)))
    except (TypeError, ValueError):
        return 5


def _auto_block_window() -> float:
    try:
        return float(max(1, int(getattr(config, "IF_AUTO_BLOCK_WINDOW_SECONDS", 300))))
    except (TypeError, ValueError):
        return 300.0


def _auto_block_ttl() -> float:
    try:
        return float(max(0, int(getattr(config, "IF_AUTO_BLOCK_TTL_SECONDS", 1800))))
    except (TypeError, ValueError):
        return 1800.0


def _limit() -> int:
    val = getattr(config, "IF_REQUESTS_PER_MINUTE", None)
    if val is not None and str(val).strip() != "":
        try:
            return int(val)
        except ValueError:
            pass
    return _DEFAULT_REQUESTS_PER_MINUTE


def _l1_capacity() -> float:
    """L1 令牌桶容量。None/未设 → 默认取 IF_REQUESTS_PER_MINUTE（与滑窗口径对齐）。"""
    val = getattr(config, "IF_RATE_TOKEN_CAPACITY", None)
    if val is None:
        return float(_limit())
    try:
        return float(val)
    except (TypeError, ValueError):
        return float(_limit())


def _l1_refill_per_sec() -> float:
    val = getattr(config, "IF_RATE_TOKEN_REFILL_PER_SEC", None)
    try:
        return max(0.0, float(val or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _l1_check(key: str, now: float) -> bool:
    """L1 秒级令牌桶检查：通过返回 True，超桶返回 False。

    - 容量<=0 视为关闭 L1（调用方先判 capacity>0 再进入）。
    - 回填按墙上时间差：tokens = min(capacity, tokens + (now-last)*refill)。
    - 每次请求扣 1 token；tokens<1 视为超桶（429）。
    - 回填为 0 时退化为纯突发桶（cap 次放行后即 429）。
    """
    capacity = _l1_capacity()
    if capacity <= 0:
        return True  # L1 关闭，交由上层滑窗判定
    refill = _l1_refill_per_sec()
    with _lock:
        bucket = _l1_token_buckets.setdefault(key, [capacity, now])
        tokens, last = bucket[0], bucket[1]
        if refill > 0 and tokens < capacity:
            elapsed = max(0.0, now - last)
            tokens = min(capacity, tokens + elapsed * refill)
        if tokens < 1.0:
            bucket[0] = tokens  # 回填后的值仍需落盘（即便被拒，已部分回填）
            bucket[1] = now
            return False
        bucket[0] = tokens - 1.0
        bucket[1] = now
        return True


# ── 真实客户端 IP 判定（安全版）────────────────────────
def get_client_ip(request: Request) -> str:
    """返回不可伪造的真实客户端 IP。

    规则：
    1. 对端（socket）不在受信代理列表 → 直接返回 socket 对端，忽略 XFF（防伪造）。
    2. 对端在受信代理列表 → 解析 XFF，从**最右**往左取第一个非受信代理、非私网段
       （追加语义下最右段由代理以 socket 追加，客户端无法伪造）。
    3. 无 XFF / 全部私网 → 回退 socket 对端。
    """
    client = request.client
    socket_host = client.host if client else "unknown"

    trusted = _trusted_proxies()
    if socket_host not in trusted:
        # 对端不受信：直接使用 socket 对端（不解析 XFF，杜绝伪造）
        return socket_host

    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        candidates = [p.strip() for p in xff.split(",") if p.strip()]
        for ip in reversed(candidates):  # 最右优先
            low = ip.lower()
            if ip in trusted:
                continue
            if low.startswith(_PRIVATE_PREFIX_HINTS):
                continue
            return ip
    return socket_host


# 向后兼容：auth.py 等旧代码引用 _client_ip
def _client_ip(request: Request) -> str:
    return get_client_ip(request)


# ── 缓存 / 规则管理 ─────────────────────────────────
def invalidate_ip_cache(ip: str | None = None) -> None:
    global _LAST_CACHE_SYNC
    with _lock:
        if ip:
            _BLOCKLIST_CACHE.pop(ip, None)
        else:
            _BLOCKLIST_CACHE.clear()
        _LAST_CACHE_SYNC = 0.0


def apply_ip_rule(ip: str, rule: dict | None) -> None:
    """把一条规则立即写入内存高速缓存（封禁毫秒级生效；rule=None 表示移除）。"""
    with _lock:
        if rule is None:
            _BLOCKLIST_CACHE.pop(ip, None)
        else:
            _BLOCKLIST_CACHE[ip] = rule


def reset_runtime_state() -> None:
    global _LAST_CACHE_SYNC
    with _lock:
        _BLOCKLIST_CACHE.clear()
        _ip_daily_records.clear()
        _rate_violations.clear()
        _l1_token_buckets.clear()
        _LAST_CACHE_SYNC = 0.0


def _get_cached_ip_rule(ip: str) -> dict | None:
    """从内存缓存获取 IP 封禁规则；未命中且缓存未超时 → 回源 DB 单行查询兜底（S3 修复）。"""
    global _LAST_CACHE_SYNC
    now = time.time()

    with _lock:
        rule = _BLOCKLIST_CACHE.get(ip)
        if rule:
            expire_at = rule.get("expire_at", 0)
            if expire_at > 0 and expire_at < now:
                _BLOCKLIST_CACHE.pop(ip, None)
            else:
                return rule

        # 定期全量同步（异步触发）
        if now - _LAST_CACHE_SYNC > _BLOCKLIST_CACHE_TTL:
            _LAST_CACHE_SYNC = now
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_sync_blocklist_cache())
            except RuntimeError:
                pass

    return None


async def _sync_blocklist_cache() -> None:
    global _LAST_CACHE_SYNC
    try:
        # P2-2: 封禁表全量同步走分页累加，避免单次 list_all(limit=2000) 在封禁表
        # 膨胀时 OOM。page_size=1000 分批拉取直至无更多，最终聚合到内存缓存。
        new_cache: dict[str, dict] = {}
        page_size = 1000
        offset = 0
        while True:
            batch = await ip_blocklist_store.list_all(limit=page_size, offset=offset)
            if not batch:
                break
            new_cache.update({r["ip"]: r for r in batch})
            offset += len(batch)
            if len(batch) < page_size:
                break
        now = time.time()
        with _lock:
            _BLOCKLIST_CACHE.clear()
            _BLOCKLIST_CACHE.update(new_cache)
            _LAST_CACHE_SYNC = now
        try:
            removed = await ip_blocklist_store.cleanup_expired()
            if removed:
                log.info("IP 封禁表过期记录清理: 删除 %d 条", removed)
        except Exception as e:
            log.warning("IP 封禁表过期清理失败: %s", e)
    except Exception as e:
        log.warning("同步 IP 封禁表缓存失败: %s", e)


async def sync_blocklist_cache() -> None:
    await _sync_blocklist_cache()


# ── 自动入黑名单 ────────────────────────────────────
def _record_auto_block_violation(ip: str, reason: str) -> None:
    """记录一次频控超限；在窗口内达到阈值后自动写入黑名单（基于真实 socket 身份）。"""
    if not _auto_block_enabled():
        return
    now = time.time()
    window = _auto_block_window()
    trigger = False
    with _lock:
        bucket = _rate_violations.setdefault(ip, [])
        bucket[:] = [t for t in bucket if now - t < window]
        bucket.append(now)
        if len(bucket) >= _auto_block_threshold():
            _rate_violations.pop(ip, None)  # 清除计数，避免重复触发
            trigger = True
    if trigger:
        log.warning("IP %s 频繁超限（窗口内 %d 次），触发自动入黑名单", ip, _auto_block_threshold())
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_auto_block_ip(ip, reason))
        except RuntimeError:
            pass


async def _auto_block_ip(ip: str, reason: str) -> None:
    try:
        rec = await ip_blocklist_store.add_or_update(
            ip=ip,
            block_type="block",
            reason=reason,
            ttl_seconds=_auto_block_ttl(),
        )
        apply_ip_rule(ip, rec)
        log.warning("安全风控: 自动封禁 %s (TTL=%ss, reason=%s)", ip, _auto_block_ttl(), reason)
    except Exception as e:
        log.warning("自动封禁 %s 失败: %s", ip, e)


# ── 主限速入口 ─────────────────────────────────────
def check_rate_limit(request: Request) -> None:
    """同步限速入口：执行动态风控（封禁/每日限额/白名单）+ L1 秒级令牌桶 + 基础滑窗限速。"""
    key = get_client_ip(request)
    now = time.time()

    # 0. 白名单：直接放行
    if key in _whitelist_ips():
        return

    # 1. 动态 IP 封禁与风控规则检查
    rule = _get_cached_ip_rule(key)
    if rule:
        b_type = rule.get("block_type", "block")
        if b_type == "block":
            # S5：对外隐藏 reason（内部配置/措施信息不外泄），reason 仅供管理面/日志
            log.warning("安全风控拦截 IP=%s reason=%s", key, rule.get("reason") or "")
            raise AppError(ErrorCodes.FORBIDDEN, "该 IP 已被系统安全风控限制访问", 403)
        if b_type == "daily_limit":
            daily_limit = int(rule.get("daily_limit", 1))
            with _lock:
                records = _ip_daily_records.setdefault(key, [])
                records[:] = [t for t in records if now - t < _DAY_SECONDS]
                if len(records) >= daily_limit:
                    raise AppError(
                        ErrorCodes.FORBIDDEN,
                        f"该 IP 触发安全风控，已被系统限制为每天最多 {daily_limit} 次调用",
                        403,
                    )
                records.append(now)

    # 2. L1 秒级令牌桶（突发限流；容量<=0 跳过，退化为仅滑窗）
    if _l1_capacity() > 0 and not _l1_check(key, now):
        _record_auto_block_violation(key, "rate-limit-exceeded")
        from .error_tracker import record as _err_record
        _err_record("RATE.001")
        raise AppError(ErrorCodes.RATE_LIMITED, f"请求过于频繁（>{_l1_capacity()} 突发令牌），请稍后重试", 429)

    # 3. 基础滑动窗口限流检查（0 = 关闭）
    limit = _limit()
    if limit <= 0:
        return

    limited = False
    with _lock:
        bucket = _ip_daily_records.setdefault(f"rate:{key}", [])
        bucket[:] = [t for t in bucket if now - t < _WINDOW_SECONDS]
        if len(bucket) >= limit:
            limited = True
        else:
            bucket.append(now)
        # 清理过期键（统一墙上时钟时间基）
        if len(_ip_daily_records) > 10000:
            expired = [
                k for k, v in _ip_daily_records.items() if not v or now - v[-1] >= max(_WINDOW_SECONDS, _DAY_SECONDS)
            ]
            for k in expired:
                _ip_daily_records.pop(k, None)

    if limited:
        _record_auto_block_violation(key, "rate-limit-exceeded")
        raise AppError(ErrorCodes.RATE_LIMITED, f"请求过于频繁（>{limit}/分钟），请稍后重试", 429)


def check_generate_request(request: Request, prompt: str = "") -> None:
    del prompt
    check_rate_limit(request)
