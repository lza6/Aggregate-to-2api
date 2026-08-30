"""后台周期任务（v4.2 拆分：main.py _run_background_tasks 迁移）。"""

from __future__ import annotations

import asyncio
import logging

from . import config
from .base64_store import enforce_quota as enforce_base64_quota
from .alerting import alert_engine
from .audit import audit_log
from .errors import ErrorCodes
from .error_tracker import count_of as _error_tracker_count_of
from .db.ip_blocklist_store import ip_blocklist_store

log = logging.getLogger("bg_tasks")


async def run_background_tasks(db, engine, registry, solver_guard, worker_health, gallery_cache) -> None:
    """TaskGroup 统一管理所有后台循环任务，组退出时自动 cancel 所有子任务。

    任一任务未捕获异常将导致整个组取消（异常传播至调用方）。
    """
    # auth_error_surge 近窗口增量：记录上一轮 count_of(AUTH.001)，求差值；
    # 差值<0 视为 error_tracker 被清空（进程重启/测试 reset），重设为 0 并从当前值重新累计。
    _auth_last = 0

    async def _cleanup_loop() -> None:
        nonlocal _auth_last
        from .worker import engine as _engine  # 复用单例（避免参数错位）

        while True:
            try:
                await asyncio.sleep(config.DB_CLEANUP_INTERVAL)
                r = await db.cleanup(config.DB_RETENTION_DAYS)  # async 方法直接 await
                log.info("DB 周期清理: %s", r)
                n = db.clean_base64_files(config.IF_BASE64_FILE_TTL)
                if n:
                    log.info("base64 文件周期清理: 删除 %d 个过期文件", n)
                # S-14: 配额保护——IF_BASE64_DIR 超过上限时按 mtime 从旧到新删至 80%
                nq = enforce_base64_quota(
                    config.IF_BASE64_DIR,
                    config.IF_IMG_MAX_GB,
                    audit_fn=lambda path, detail: audit_log.record("img.gc.quota", "system", path, detail),
                )
                if nq:
                    log.info("base64 配额保护: 删除 %d 个超限文件（上限 %.1fGB）", nq, config.IF_IMG_MAX_GB)
                if config.IF_IDEMPOTENCY_ENABLED:
                    nd = await db.clean_expired_idempotency()
                    if nd:
                        log.info("幂等 key 周期清理: 删除 %d 个过期条目", nd)
                if config.IF_DLQ_ENABLED:
                    ndlq = await db.clean_expired_dlq()
                    if ndlq:
                        log.info("死信队列周期清理: 删除 %d 个过期条目", ndlq)
                nc = await db.clean_expired_cache()
                if nc:
                    log.info("缓存表周期清理: 删除 %d 个过期条目", nc)
                if config.IF_PERSISTENT_QUEUE_ENABLED and _engine._queue_db:
                    nq = await _engine._queue_db.cleanup()
                    if nq.get("deleted"):
                        log.info("持久化队列周期清理: 删除 %d 个过期条目", nq["deleted"])
                snap = engine.snapshot()
                ssnap = solver_guard.snapshot()
                stats = await db.stats_overview()
                _auth_now = _error_tracker_count_of(ErrorCodes.UNAUTHORIZED)
                _auth_delta = _auth_now - _auth_last
                if _auth_delta < 0:  # error_tracker 被清空（重启/reset）→ 从当前值重新累计
                    _auth_delta = 0
                _auth_last = _auth_now
                ctx = {
                    "queued": snap["queued"],
                    "solver_circuit_open": ssnap.get("circuit_open", False),
                    "token_pool_empty": engine.token_pool.qsize() == 0,
                    "window_requests": stats.get("total_requests", 0),
                    "window_errors": stats.get("total_errors", 0),
                    # Section 16 可观测性：告警上下文扩充
                    "max_consecutive_failures": max(
                        (registry._consecutive_failures.get(p, 0) for p in registry.providers),
                        default=0,
                    ),
                    "auth_error_count": _auth_delta,  # 近窗口增量（防累计值永真）
                }
                # IP 批量封禁/限流计数（异步读 DB，失败静默保持 0）
                try:
                    ctx["blocked_ip_count"] = len(await ip_blocklist_store.list_all(limit=2000))
                except Exception:
                    ctx["blocked_ip_count"] = 0
                alert_engine.evaluate(ctx)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("DB 周期清理失败: %s", e)

    async def _health_check_loop(interval: float = 60.0) -> None:
        if not config.IF_HEALTH_CHECK_ENABLED:
            return
        while True:
            try:
                await asyncio.sleep(interval)
                await registry.health_check_all()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("健康探测循环异常: %s", e)

    async def _provider_recover_loop() -> None:
        while True:
            try:
                await asyncio.sleep(config.IF_PROVIDER_RECOVER_INTERVAL)
                registry.try_recover_all()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("provider 恢复探测循环异常: %s", e)

    async def _worker_sweep_loop() -> None:
        """S-7: worker 心跳巡检（30s 一轮，标记超期未活跃 worker 为 stale）。"""
        while True:
            try:
                await asyncio.sleep(30)
                newly = worker_health.sweep()
                if newly:
                    log.warning("worker 卡死巡检: %d 个 worker 超期未活跃（stale）: %s", len(newly), newly)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("worker 巡检循环异常: %s", e)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(_cleanup_loop())
        if config.IF_HEALTH_CHECK_ENABLED:
            tg.create_task(_health_check_loop(config.IF_HEALTH_CHECK_INTERVAL))
        tg.create_task(_provider_recover_loop())
        tg.create_task(_worker_sweep_loop())
