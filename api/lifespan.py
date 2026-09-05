"""应用生命周期管理（v4.2 拆分：main.py lifespan 迁移）。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from . import config, imagefree_client, turnstile_client
from .base64_store import ensure_dir as ensure_base64_dir
from .bg_tasks import run_background_tasks
from .cache_warmup import warmup_cache
from .disk_logger import setup_disk_logging, teardown_disk_logging
from .log_ws import ws_log_handler
from .meta import (
    _prev_engine,
    db,
    engine,
    gallery_cache,
    providers_bootstrap,
    registry,
    shutdown_phase,
)
from .solver_guard import solver_guard
from .telemetry import init_telemetry, shutdown_telemetry
from .worker_health import worker_health

log = logging.getLogger("imagefree_api")


@asynccontextmanager
async def lifespan(_app):
    # IMP-08: 启动 OTel 追踪
    init_telemetry()
    # U-02: 注入 WebSocket 与内存缓冲日志处理器
    root_l = logging.getLogger()
    root_l.setLevel(logging.INFO)
    from .log_buffer import log_buffer

    root_l.addHandler(log_buffer)
    root_l.addHandler(ws_log_handler)
    for _name in ("imagefree_api", "dispatch", "dispatch_edit", "worker", "routes", "uvicorn", "uvicorn.access"):
        _l = logging.getLogger(_name)
        _l.setLevel(logging.INFO)
        if log_buffer not in _l.handlers:
            _l.addHandler(log_buffer)
        if ws_log_handler not in _l.handlers:
            _l.addHandler(ws_log_handler)
    # P13: 磁盘日志落盘
    _disk_log_handler = setup_disk_logging(config.IF_LOG_DIR, config.IF_LOG_RETENTION_DAYS)
    log.info("磁盘日志已启用: %s（保留 %d 天）", config.IF_LOG_DIR, config.IF_LOG_RETENTION_DAYS)

    await engine.start()
    gallery_cache.start_reaper()
    restored = await gallery_cache.restore_from_db()
    if restored:
        log.info("缓存从 DB 恢复完成: %d 个条目", restored)
    # ISSUE-02: 启动即加载 IP 封禁表 → 内存高速缓存，重启后风控立刻生效
    from .request_guard import sync_blocklist_cache

    try:
        await sync_blocklist_cache()
    except Exception as e:
        log.warning("IP 封禁表缓存预热失败（可忽略）: %s", e)
    _warmup_task = asyncio.create_task(warmup_cache(gallery_cache, db))
    _background_task = asyncio.create_task(
        run_background_tasks(db, engine, registry, solver_guard, worker_health, gallery_cache)
    )
    _batch_timer_task = None
    _checkpoint_timer_task = None
    if config.IF_DB_BATCH_ENABLED:
        _batch_timer_task = asyncio.create_task(db.start_batch_timer())
    _checkpoint_timer_task = asyncio.create_task(db.start_checkpoint_timer())

    providers_bootstrap()
    imagefree_provider = registry.providers.get("imagefree")
    if imagefree_provider:
        from .meta import _prev_engine_fallback

        _prev_engine_fallback(imagefree_provider, engine)

    from .proxy_pool import proxy_pool

    if config.PROXY_FILE:
        proxy_pool.load_file(config.PROXY_FILE)
    aifree = registry.providers.get("aifreeforever")
    if aifree:
        aifree._proxy_pool = proxy_pool
    # fal.ai minimax-H3-max：注入代理池（每 IP 5 次/天额度轮换）
    falai = registry.providers.get("falai")
    if falai:
        falai._proxy_pool = proxy_pool

    from .free_proxy_fetcher import free_proxy_fetcher

    await free_proxy_fetcher.start()

    # Cloudflare trace 出口探测器（v6.7.x）：IF_PROXY_TRACE_ENABLED 控启停
    from .proxy_tracer import proxy_tracer

    proxy_tracer.pool = proxy_pool  # 延迟绑定 pool
    await proxy_tracer.start()

    if config.ACCOUNT_AUTO:
        from . import registerer
        from .account_pool import account_pool

        account_pool.registerers.update(registerer.build_registerers())
        await account_pool.start()

    from .providers.registry import startup_all as providers_startup

    await providers_startup()
    ensure_base64_dir()
    try:
        n = db.clean_base64_files(config.IF_BASE64_FILE_TTL)
        if n:
            log.info("base64 文件启动清理: 删除 %d 个过期文件", n)
    except Exception as e:
        log.warning("base64 文件启动清理失败（可忽略）: %s", e)
    try:
        r = await db.cleanup(config.DB_RETENTION_DAYS)
        log.info("DB 启动清理: %s", r)
    except Exception as e:
        log.warning("DB 启动清理失败（可忽略）: %s", e)

    from .provider_probe import provider_probe

    await provider_probe.start(interval_seconds=180)

    yield
    log.info("优雅关闭开始: 分阶段有序停止服务")
    await provider_probe.stop()

    from .providers.registry import shutdown_all as providers_shutdown

    async def _stop_warmup() -> None:
        if _warmup_task and not _warmup_task.done():
            _warmup_task.cancel()
            try:
                await _warmup_task
            except asyncio.CancelledError:
                pass

    async def _stop_batch_timer() -> None:
        if _batch_timer_task:
            _batch_timer_task.cancel()
            try:
                await _batch_timer_task
            except asyncio.CancelledError:
                pass

    async def _stop_checkpoint_timer() -> None:
        if _checkpoint_timer_task:
            _checkpoint_timer_task.cancel()
            try:
                await _checkpoint_timer_task
            except asyncio.CancelledError:
                pass

    async def _stop_background() -> None:
        _background_task.cancel()
        try:
            await _background_task
        except ExceptionGroup:
            pass

    await shutdown_phase(
        5.0, "① 后台任务停止", _stop_warmup(), _stop_batch_timer(), _stop_background(), _stop_checkpoint_timer()
    )

    async def _flush_db() -> None:
        await db.flush()

    await shutdown_phase(3.0, "② DB 写缓冲刷新", _flush_db())
    await shutdown_phase(10.0, "③ Worker 停止", engine.stop())

    # v7.6 P0：非 imagefree 生成任务（nanobanana/aifreeforever/falai）是 asyncio.create_task
    # 挂 _PROVIDER_TASKS，不 drain 则重启时被硬取消、结果不落库（客户端永久 pending）。
    # 放在 Provider 停止之前、DB 关闭之前，给在途任务足够时间落库。
    async def _drain_provider_tasks() -> None:
        from .dispatch import _PROVIDER_TASKS

        tasks = list(_PROVIDER_TASKS)
        if not tasks:
            return
        await asyncio.gather(*tasks, return_exceptions=True)

    await shutdown_phase(8.0, "③.5 非 imagefree 在途任务排空", _drain_provider_tasks())


    async def _restore_engine() -> None:
        await providers_shutdown()
        _imgf = registry.providers.get("imagefree")
        if _imgf is not None:
            if _prev_engine is not None:
                _imgf.engine = _prev_engine
            else:
                _imgf.engine = None
                try:
                    delattr(_imgf, "engine")
                except AttributeError:
                    pass

    await shutdown_phase(8.0, "④ Provider 停止", _restore_engine())

    from .account_pool import account_pool as _ap
    from .free_proxy_fetcher import free_proxy_fetcher as _fpf
    from .proxy_tracer import proxy_tracer as _pt

    await shutdown_phase(5.0, "⑤ 代理/号池停止", _fpf.stop(), _ap.stop(), _pt.stop())

    async def _flush_cache() -> None:
        await gallery_cache.flush_to_db()

    await shutdown_phase(3.0, "⑥ 缓存持久化", _flush_cache(), gallery_cache.stop_reaper())

    # P1-B: 关闭前等待 SSE 发布任务完成，防止终态事件丢失
    from .sse_events import await_pending_sse_tasks

    await shutdown_phase(5.0, "⑥.5 SSE 发布任务排空", await_pending_sse_tasks())

    await shutdown_phase(3.0, "⑦ HTTP 连接池关闭", turnstile_client.close_client(), imagefree_client.close_client())

    # v7.7 P2：ecosystem 共享 httpx client 此前定义了 close_client 却无人调用（停机不释放连接池）
    from .routes import ecosystem as _eco

    await shutdown_phase(2.0, "⑦.5 生态页连接池关闭", _eco.close_client())

    async def _shutdown_otel() -> None:
        shutdown_telemetry()

    await shutdown_phase(2.0, "⑧ OTel 关闭", _shutdown_otel())

    async def _close_db() -> None:
        await db.close()

    await shutdown_phase(3.0, "⑨ DB 连接池关闭", _close_db())

    logging.getLogger().removeHandler(ws_log_handler)
    teardown_disk_logging(_disk_log_handler)
    log.info("优雅关闭完成")
