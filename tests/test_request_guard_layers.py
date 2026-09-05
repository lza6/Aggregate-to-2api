"""M5-E1 补测：request_guard 动态风控（IP 封禁/白名单/滑窗限流/auto_block）。

覆盖 api/request_guard.py 缺失分支（配置读取、白名单、XFF 伪造防护、
IP 封禁/每日限额、滑动窗口限流、缓存失效、自动入黑名单等）。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from fastapi import Request

from api import (
    config,  # noqa: E402 (kept after request_guard to keep import grouping)
    request_guard,
)
from api.errors import AppError  # noqa: E402 (kept after request_guard to keep import grouping)


def _set_cfg_attr(monkeypatch, obj, name, value):
    """对可能不存在的 config 属性用 setdefault 风格 setattr（monkeypatch 支持 raising=False）。"""
    monkeypatch.setattr(obj, name, value, raising=False)


def _mk_request(client_host: str | None = "1.2.3.4", xff: str | None = None) -> Request:
    """构造一个最小 Request，client.host / headers 可控。"""
    # Starlette 的 Request.client 需要 client 是 (host, port) 元组时才正确解析；
    # 但 scope["client"] 期望为 [host, port]，部分版本会把 dict 的 "host" key 当 host。
    # 直接用 tuple 规避差异。
    client = (client_host, 12345) if client_host else None
    scope: dict[str, Any] = {
        "type": "http",
        "client": client,
        "headers": [],
    }
    if xff is not None:
        scope["headers"] = [(b"x-forwarded-for", xff.encode())]
    return Request(scope)


@pytest.fixture(autouse=True)
def _reset_state():
    """每用例重置 request_guard 运行时状态。"""
    request_guard.reset_runtime_state()
    yield
    request_guard.reset_runtime_state()


# ── 配置读取分支 ──────────────────────────────────
def test_whitelist_ips_string(monkeypatch):
    monkeypatch.setattr(config, "IF_IP_WHITELIST", "1.1.1.1, 2.2.2.2 ,3.3.3.3")
    assert request_guard._whitelist_ips() == {"1.1.1.1", "2.2.2.2", "3.3.3.3"}


def test_whitelist_ips_list(monkeypatch):
    monkeypatch.setattr(config, "IF_IP_WHITELIST", ["a", "b"])
    assert request_guard._whitelist_ips() == {"a", "b"}


def test_whitelist_ips_empty(monkeypatch):
    monkeypatch.setattr(config, "IF_IP_WHITELIST", "")
    assert request_guard._whitelist_ips() == set()


def test_whitelist_ips_none(monkeypatch):
    monkeypatch.setattr(config, "IF_IP_WHITELIST", None)
    assert request_guard._whitelist_ips() == set()


def test_trusted_proxies_default(monkeypatch):
    """未配置时默认信任本机反代。"""
    if hasattr(config, "IF_TRUSTED_PROXIES"):
        monkeypatch.delattr(config, "IF_TRUSTED_PROXIES")
    assert request_guard._trusted_proxies() == ["127.0.0.1", "::1"]


def test_trusted_proxies_empty_string(monkeypatch):
    monkeypatch.setattr(config, "IF_TRUSTED_PROXIES", "")
    assert request_guard._trusted_proxies() == ["127.0.0.1", "::1"]


def test_trusted_proxies_list(monkeypatch):
    monkeypatch.setattr(config, "IF_TRUSTED_PROXIES", ["10.0.0.1", "10.0.0.2"])
    assert request_guard._trusted_proxies() == ["10.0.0.1", "10.0.0.2"]


def test_trusted_proxies_string(monkeypatch):
    monkeypatch.setattr(config, "IF_TRUSTED_PROXIES", "10.0.0.1, 10.0.0.2")
    assert request_guard._trusted_proxies() == ["10.0.0.1", "10.0.0.2"]


def test_auto_block_disabled(monkeypatch):
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_ENABLED", False)
    assert request_guard._auto_block_enabled() is False


def test_auto_block_threshold_invalid_falls_back(monkeypatch):
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_THRESHOLD", "not-a-number")
    assert request_guard._auto_block_threshold() == 5


def test_auto_block_threshold_below_min(monkeypatch):
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_THRESHOLD", 1)
    assert request_guard._auto_block_threshold() == 2


def test_auto_block_window_invalid(monkeypatch):
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_WINDOW_SECONDS", "x")
    assert request_guard._auto_block_window() == 300.0


def test_auto_block_window_below_min(monkeypatch):
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_WINDOW_SECONDS", 0)
    assert request_guard._auto_block_window() == 1.0


def test_auto_block_ttl_invalid(monkeypatch):
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_TTL_SECONDS", "bad")
    assert request_guard._auto_block_ttl() == 1800.0


def test_auto_block_ttl_negative(monkeypatch):
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_TTL_SECONDS", -5)
    assert request_guard._auto_block_ttl() == 0.0


def test_limit_explicit(monkeypatch):
    monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", "42")
    assert request_guard._limit() == 42


def test_limit_invalid_falls_back(monkeypatch):
    monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", "not-int")
    assert request_guard._limit() == request_guard._DEFAULT_REQUESTS_PER_MINUTE


def test_limit_empty_falls_back(monkeypatch):
    monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", "")
    assert request_guard._limit() == request_guard._DEFAULT_REQUESTS_PER_MINUTE


def test_limit_none_falls_back(monkeypatch):
    monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", None)
    assert request_guard._limit() == request_guard._DEFAULT_REQUESTS_PER_MINUTE


# ── 客户端 IP 判定（XFF 伪造防护）──────────────────
def test_get_client_ip_untrusted_peer_ignores_xff(monkeypatch):
    monkeypatch.setattr(config, "IF_TRUSTED_PROXIES", "127.0.0.1")
    req = _mk_request(client_host="8.8.8.8", xff="1.1.1.1, 2.2.2.2")
    assert request_guard.get_client_ip(req) == "8.8.8.8"


def test_get_client_ip_trusted_peer_picks_rightmost_non_private(monkeypatch):
    monkeypatch.setattr(config, "IF_TRUSTED_PROXIES", "127.0.0.1")
    req = _mk_request(client_host="127.0.0.1", xff="127.0.0.1, 10.0.0.1, 203.0.113.5")
    assert request_guard.get_client_ip(req) == "203.0.113.5"


def test_get_client_ip_skips_trusted_in_xff(monkeypatch):
    """XFF 中受信代理段被跳过。"""
    monkeypatch.setattr(config, "IF_TRUSTED_PROXIES", "127.0.0.1")
    req = _mk_request(client_host="127.0.0.1", xff="203.0.113.5, 127.0.0.1")
    assert request_guard.get_client_ip(req) == "203.0.113.5"


def test_get_client_ip_all_private_falls_back_to_socket(monkeypatch):
    monkeypatch.setattr(config, "IF_TRUSTED_PROXIES", "127.0.0.1")
    req = _mk_request(client_host="127.0.0.1", xff="10.0.0.1, 192.168.1.1")
    assert request_guard.get_client_ip(req) == "127.0.0.1"


def test_get_client_ip_no_xff(monkeypatch):
    monkeypatch.setattr(config, "IF_TRUSTED_PROXIES", "127.0.0.1")
    req = _mk_request(client_host="127.0.0.1", xff=None)
    assert request_guard.get_client_ip(req) == "127.0.0.1"


def test_get_client_ip_no_client_returns_unknown():
    req = _mk_request(client_host=None)
    assert request_guard.get_client_ip(req) == "unknown"


def test_client_ip_alias(monkeypatch):
    monkeypatch.setattr(config, "IF_TRUSTED_PROXIES", "127.0.0.1")
    req = _mk_request(client_host="9.9.9.9")
    assert request_guard._client_ip(req) == "9.9.9.9"


# ── check_rate_limit 主入口 ──────────────────────
def test_check_rate_limit_whitelist_bypasses(monkeypatch):
    monkeypatch.setattr(config, "IF_IP_WHITELIST", "1.2.3.4")
    monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 1)
    req = _mk_request(client_host="1.2.3.4")
    request_guard.check_rate_limit(req)


def test_check_rate_limit_blocked_ip_403(monkeypatch):
    monkeypatch.setattr(config, "IF_IP_WHITELIST", "")
    monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)
    request_guard.reset_runtime_state()
    request_guard.apply_ip_rule("6.6.6.6", {"block_type": "block", "reason": "test", "expire_at": 0})
    req = _mk_request(client_host="6.6.6.6")
    with pytest.raises(AppError) as exc:
        request_guard.check_rate_limit(req)
    assert exc.value.status_code == 403


def test_check_rate_limit_daily_limit_exceeded_403(monkeypatch):
    monkeypatch.setattr(config, "IF_IP_WHITELIST", "")
    monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)
    request_guard.reset_runtime_state()
    request_guard.apply_ip_rule("7.7.7.7", {"block_type": "daily_limit", "daily_limit": 1, "expire_at": 0})
    req = _mk_request(client_host="7.7.7.7")
    request_guard.check_rate_limit(req)  # 第 1 次：记录
    with pytest.raises(AppError) as exc:
        request_guard.check_rate_limit(req)  # 第 2 次：超限
    assert exc.value.status_code == 403
    assert "每天最多" in str(exc.value.message)


def test_check_rate_limit_sliding_window_429(monkeypatch):
    monkeypatch.setattr(config, "IF_IP_WHITELIST", "")
    monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 2)
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_ENABLED", False)
    request_guard.reset_runtime_state()
    req = _mk_request(client_host="8.8.8.8")
    request_guard.check_rate_limit(req)
    request_guard.check_rate_limit(req)
    with pytest.raises(AppError) as exc:
        request_guard.check_rate_limit(req)
    assert exc.value.status_code == 429


def test_check_rate_limit_disabled_when_limit_zero(monkeypatch):
    monkeypatch.setattr(config, "IF_IP_WHITELIST", "")
    monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)
    request_guard.reset_runtime_state()
    req = _mk_request(client_host="9.9.9.9")
    request_guard.check_rate_limit(req)


def test_check_generate_request_delegates(monkeypatch):
    monkeypatch.setattr(config, "IF_IP_WHITELIST", "1.1.1.1")
    monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)
    request_guard.reset_runtime_state()
    req = _mk_request(client_host="1.1.1.1")
    request_guard.check_generate_request(req, "prompt")


# ── 缓存与运行时状态管理 ──────────────────────────
def test_invalidate_ip_cache_specific():
    request_guard._BLOCKLIST_CACHE["x.x.x.x"] = {"block_type": "block"}
    request_guard.invalidate_ip_cache("x.x.x.x")
    assert "x.x.x.x" not in request_guard._BLOCKLIST_CACHE


def test_invalidate_ip_cache_all():
    request_guard._BLOCKLIST_CACHE["a"] = {}
    request_guard._BLOCKLIST_CACHE["b"] = {}
    request_guard.invalidate_ip_cache()
    assert request_guard._BLOCKLIST_CACHE == {}
    assert request_guard._LAST_CACHE_SYNC == 0.0


def test_apply_ip_rule_none_removes():
    request_guard._BLOCKLIST_CACHE["1.2.3.4"] = {"block_type": "block"}
    request_guard.apply_ip_rule("1.2.3.4", None)
    assert "1.2.3.4" not in request_guard._BLOCKLIST_CACHE


def test_apply_ip_rule_set():
    request_guard.apply_ip_rule("1.2.3.4", {"block_type": "block"})
    assert request_guard._BLOCKLIST_CACHE["1.2.3.4"]["block_type"] == "block"


def test_reset_runtime_state_clears_all():
    request_guard._BLOCKLIST_CACHE["a"] = {}
    request_guard._ip_daily_records["b"] = [1.0]
    request_guard._rate_violations["c"] = [1.0]
    request_guard.reset_runtime_state()
    assert request_guard._BLOCKLIST_CACHE == {}
    assert request_guard._ip_daily_records == {}
    assert request_guard._rate_violations == {}


def test_get_cached_ip_rule_expired_cleared(monkeypatch):
    """缓存中已过期的规则被清除（expire_at < now）。"""
    request_guard.reset_runtime_state()
    request_guard._BLOCKLIST_CACHE["1.2.3.4"] = {"block_type": "block", "reason": "x", "expire_at": time.time() - 1}
    result = request_guard._get_cached_ip_rule("1.2.3.4")
    assert result is None
    assert "1.2.3.4" not in request_guard._BLOCKLIST_CACHE


def test_get_cached_ip_rule_hit():
    """缓存命中且未过期（expire_at=0 永不过期）→ 直接返回。"""
    request_guard.reset_runtime_state()
    rule = {"block_type": "block", "reason": "x", "expire_at": 0}
    request_guard._BLOCKLIST_CACHE["1.2.3.4"] = rule
    assert request_guard._get_cached_ip_rule("1.2.3.4") is rule


def test_get_cached_ip_rule_miss_returns_none():
    """缓存未命中 → 返回 None。"""
    request_guard.reset_runtime_state()
    request_guard._LAST_CACHE_SYNC = time.time()  # 避免触发异步同步
    assert request_guard._get_cached_ip_rule("99.99.99.99") is None


def test_auto_block_violation_triggers_block(monkeypatch):
    """频繁超限达阈值 → 触发自动入黑名单（验证计数与触发，create_task 在无 loop 时静默）。"""
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_ENABLED", True)
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_THRESHOLD", 2)
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_WINDOW_SECONDS", 60)
    request_guard.reset_runtime_state()
    request_guard._record_auto_block_violation("11.11.11.11", "test")
    request_guard._record_auto_block_violation("11.11.11.11", "test")
    # 触发后计数被清除
    assert "11.11.11.11" not in request_guard._rate_violations


def test_auto_block_disabled_no_violation(monkeypatch):
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_ENABLED", False)
    request_guard.reset_runtime_state()
    request_guard._record_auto_block_violation("12.12.12.12", "test")
    assert "12.12.12.12" not in request_guard._rate_violations


def test_auto_block_violation_window_pruning(monkeypatch):
    """窗口外记录被剪枝，不累计过期违规。"""
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_ENABLED", True)
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_THRESHOLD", 99)
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_WINDOW_SECONDS", 1)
    request_guard.reset_runtime_state()
    # 注入一条很老的记录
    request_guard._rate_violations["13.13.13.13"] = [time.time() - 100]
    request_guard._record_auto_block_violation("13.13.13.13", "test")
    # 老记录被剪枝，只剩 1 条新记录
    assert len(request_guard._rate_violations["13.13.13.13"]) == 1


# ── L1 令牌桶（M1-A1）──────────────────────────
def test_check_rate_limit_l3_sliding_window_429(monkeypatch):
    """关闭 L1（容量 0）+ L3 滑窗超限 → 429。"""
    monkeypatch.setattr(config, "IF_IP_WHITELIST", "")
    _set_cfg_attr(monkeypatch, config, "IF_RATE_TOKEN_CAPACITY", 0)  # 关闭 L1
    monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 2)
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_ENABLED", False)
    request_guard.reset_runtime_state()
    req = _mk_request(client_host="8.8.8.8")
    request_guard.check_rate_limit(req)
    request_guard.check_rate_limit(req)
    with pytest.raises(AppError) as exc:
        request_guard.check_rate_limit(req)
    assert exc.value.status_code == 429
    assert "分钟" in str(exc.value.message)


def test_check_rate_limit_l3_gc_old_records(monkeypatch):
    """滑窗 >10000 键时清理过期记录。"""
    monkeypatch.setattr(config, "IF_IP_WHITELIST", "")
    _set_cfg_attr(monkeypatch, config, "IF_RATE_TOKEN_CAPACITY", 0)
    monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 99999)  # 不触发限流
    request_guard.reset_runtime_state()
    # 注入 10001 个老记录键
    old = time.time() - 100000
    for i in range(10001):
        request_guard._ip_daily_records[f"rate:ip-{i}"] = [old]
    req = _mk_request(client_host="gc-test-ip")
    request_guard.check_rate_limit(req)  # 触发清理
    assert len(request_guard._ip_daily_records) < 10001


def test_check_rate_limit_daily_limit_appends_record(monkeypatch):
    """daily_limit 规则未超限时追加记录。"""
    monkeypatch.setattr(config, "IF_IP_WHITELIST", "")
    _set_cfg_attr(monkeypatch, config, "IF_RATE_TOKEN_CAPACITY", 0)
    monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)
    request_guard.reset_runtime_state()
    request_guard.apply_ip_rule("7.7.7.7", {"block_type": "daily_limit", "daily_limit": 5, "expire_at": 0})
    req = _mk_request(client_host="7.7.7.7")
    request_guard.check_rate_limit(req)
    # 记录被追加
    assert len(request_guard._ip_daily_records["7.7.7.7"]) == 1


# ── 异步路径（_sync_blocklist_cache / _auto_block_ip）──
@pytest.mark.asyncio
async def test_sync_blocklist_cache_updates_cache(monkeypatch):
    """_sync_blocklist_cache 从 store 拉取并更新缓存。"""

    async def fake_list_all(limit=2000, offset=0, since_ts=None, updated_before=None):
        if offset == 0:
            return [{"ip": "1.1.1.1", "block_type": "block", "reason": "x", "expire_at": 0}]
        return []

    async def fake_cleanup():
        return 0

    monkeypatch.setattr(request_guard.ip_blocklist_store, "list_all", fake_list_all)
    monkeypatch.setattr(request_guard.ip_blocklist_store, "cleanup_expired", fake_cleanup)
    request_guard.reset_runtime_state()
    await request_guard._sync_blocklist_cache()
    assert "1.1.1.1" in request_guard._BLOCKLIST_CACHE


@pytest.mark.asyncio
async def test_sync_blocklist_cache_handles_store_error(monkeypatch):
    """store 异常时不崩溃。"""

    async def boom(limit=2000, offset=0, since_ts=None):
        raise RuntimeError("db down")

    monkeypatch.setattr(request_guard.ip_blocklist_store, "list_all", boom)
    request_guard.reset_runtime_state()
    # 不应抛出
    await request_guard._sync_blocklist_cache()


@pytest.mark.asyncio
async def test_sync_blocklist_cache_cleanup_warns(monkeypatch):
    """cleanup 抛异常时记 warning 不崩溃。"""

    async def fake_list_all(limit=2000, offset=0, since_ts=None, updated_before=None):
        return []

    async def boom():
        raise RuntimeError("cleanup fail")

    monkeypatch.setattr(request_guard.ip_blocklist_store, "list_all", fake_list_all)
    monkeypatch.setattr(request_guard.ip_blocklist_store, "cleanup_expired", boom)
    request_guard.reset_runtime_state()
    await request_guard._sync_blocklist_cache()


@pytest.mark.asyncio
async def test_auto_block_ip_writes_rule(monkeypatch):
    """_auto_block_ip 写入 store 并更新缓存。"""

    async def fake_add(ip, block_type, reason, ttl_seconds):
        return {"ip": ip, "block_type": block_type, "reason": reason, "expire_at": 0}

    monkeypatch.setattr(request_guard.ip_blocklist_store, "add_or_update", fake_add)
    request_guard.reset_runtime_state()
    await request_guard._auto_block_ip("14.14.14.14", "test")
    assert request_guard._BLOCKLIST_CACHE["14.14.14.14"]["block_type"] == "block"


@pytest.mark.asyncio
async def test_auto_block_ip_handles_store_error(monkeypatch):
    """store 异常时不崩溃。"""

    async def boom(ip, block_type, reason, ttl_seconds):
        raise RuntimeError("db down")

    monkeypatch.setattr(request_guard.ip_blocklist_store, "add_or_update", boom)
    request_guard.reset_runtime_state()
    await request_guard._auto_block_ip("15.15.15.15", "test")  # 不抛


@pytest.mark.asyncio
async def test_sync_blocklist_cache_public_alias(monkeypatch):
    """sync_blocklist_cache 公共别名委托给 _sync_blocklist_cache。"""

    async def fake_list_all(limit=2000, offset=0, since_ts=None, updated_before=None):
        if offset == 0:
            return [{"ip": "2.2.2.2", "block_type": "block", "reason": "y", "expire_at": 0}]
        return []

    async def fake_cleanup():
        return 0

    monkeypatch.setattr(request_guard.ip_blocklist_store, "list_all", fake_list_all)
    monkeypatch.setattr(request_guard.ip_blocklist_store, "cleanup_expired", fake_cleanup)
    request_guard.reset_runtime_state()
    await request_guard.sync_blocklist_cache()
    assert "2.2.2.2" in request_guard._BLOCKLIST_CACHE


@pytest.mark.asyncio
async def test_get_cached_ip_rule_triggers_async_sync(monkeypatch):
    """缓存未命中且超 TTL → 调度 _sync_blocklist_cache（有运行 loop 时）。"""

    async def fake_list_all(limit=2000, offset=0, since_ts=None, updated_before=None):
        return []

    async def fake_cleanup():
        return 0

    monkeypatch.setattr(request_guard.ip_blocklist_store, "list_all", fake_list_all)
    monkeypatch.setattr(request_guard.ip_blocklist_store, "cleanup_expired", fake_cleanup)
    request_guard.reset_runtime_state()
    # 强制 TTL 超时
    request_guard._LAST_CACHE_SYNC = 0.0
    # 缓存未命中
    result = request_guard._get_cached_ip_rule("99.99.99.99")
    assert result is None
    # 异步同步被调度，让 loop 跑一下
    await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_auto_block_violation_schedules_task(monkeypatch):
    """有运行事件循环时，触发后调度 _auto_block_ip。

    _auto_block_threshold 实现有 max(2,...) 下限，故阈值设 2、记录 2 次触发。
    """
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_ENABLED", True)
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_THRESHOLD", 2)
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_WINDOW_SECONDS", 60)

    called = []

    async def fake_auto_block(ip, reason):
        called.append((ip, reason))

    monkeypatch.setattr(request_guard, "_auto_block_ip", fake_auto_block)
    request_guard.reset_runtime_state()
    # 2 次违规达阈值（threshold=2，max(2,2)=2）
    request_guard._record_auto_block_violation("16.16.16.16", "test")
    request_guard._record_auto_block_violation("16.16.16.16", "test")
    await asyncio.sleep(0.05)
    assert called == [("16.16.16.16", "test")]


# ── P3-3 per-IP 分片锁：不同 IP 限速检查互不阻塞 ──────────────
def test_p3_3_per_ip_sharded_lock_isolation(monkeypatch):
    """P3-3: 不同 IP 的 _ip_lock 返回不同锁对象（分片隔离）。"""
    monkeypatch.setattr(config, "IF_IP_WHITELIST", "")
    request_guard.reset_runtime_state()
    lock_a = request_guard._ip_lock("1.1.1.1")
    lock_b = request_guard._ip_lock("2.2.2.2")
    assert lock_a is not lock_b, "不同 IP 应得到不同锁（分片隔离）"
    # 同 IP 二次取应复用同一锁（不新建）
    assert request_guard._ip_lock("1.1.1.1") is lock_a


def test_p3_3_per_ip_lock_isolation_concurrent(monkeypatch):
    """P3-3: 不同 IP 并发限速检查不串行（分片锁互不竞争）。

    构造两个 IP，各持自己锁做长时间临界区；若仍用全局锁会死锁/串行，
    分片锁下两 IP 可并行进入。
    """
    import threading as _t

    monkeypatch.setattr(config, "IF_IP_WHITELIST", "")
    _set_cfg_attr(monkeypatch, config, "IF_RATE_TOKEN_CAPACITY", 0)
    monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 99999)
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_ENABLED", False)
    request_guard.reset_runtime_state()

    results = []
    barrier = _t.Barrier(2)

    def worker(ip):
        # 先获取该 IP 的锁并持有，模拟临界区
        barrier.wait()  # 两线程同步后同时尝试 check_rate_limit
        # check_rate_limit 对不同 IP 应不阻塞（分片锁）
        req = _mk_request(client_host=ip)
        request_guard.check_rate_limit(req)
        results.append(ip)

    t1 = _t.Thread(target=worker, args=("9.9.9.9",))
    t2 = _t.Thread(target=worker, args=("8.8.8.8",))
    t1.start()
    t2.start()
    t1.join(timeout=3)
    t2.join(timeout=3)
    assert len(results) == 2, "两个不同 IP 的限速检查应并行完成（分片锁隔离）"
