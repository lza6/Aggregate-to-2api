"""图生图编辑路由与跨进程互斥（v4.2 拆分：main.py 迁移）。

上游 ai-photo-editor 硬并发=1（同出口 IP 只能 1 个编辑任务在途），本模块承载
双层互斥：进程内 asyncio.Lock + 跨进程文件锁，保障多进程/多实例不撞上游。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import uuid

from . import config
from . import imagefree_client
from .models import EditRequest, TaskInfo
from .meta import db, engine, registry, gallery_cache
from .errors import AppError, ErrorCodes
from .db import task_to_public
from .dispatch import _normalize_model, _provider_prefix, _parse_input_image, _parse_input_images, _validate_model, _PROVIDER_TASKS, _provider_sem
from .db.lease_store import LeaseStore

log = logging.getLogger("dispatch_edit")


# ── 图生图全局串行锁 ──
_EDIT_LOCK = asyncio.Lock()
_EDIT_PENDING: set[str] = set()
_EDIT_MUTEX_DIR = os.path.join(os.path.dirname(config.DB_FILE) or ".", ".edit_locks")


# ── 跨进程图生图互斥（文件锁）──
def _edit_mutex_path(key: str) -> str:
    safe = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(_EDIT_MUTEX_DIR, f"edit-{safe}.lock")


def _edit_mutex_stale(path: str) -> bool:
    """锁文件是否过期（持有进程已死 或 超过 EDIT_LOCK_MAX_AGE）。"""
    try:
        with open(path, encoding="utf-8") as f:
            parts = f.read().split()
        if len(parts) < 3:
            return True
        pid, ts, _tok = int(parts[0]), float(parts[1]), parts[2]
    except (OSError, ValueError, IndexError):
        return True
    if time.time() - ts > config.EDIT_LOCK_MAX_AGE:
        return True
    # Docker 容器内 PID 1 是 init 进程，os.kill(1,0) 返回 PermissionError 而非 ProcessLookupError，
    # 导致锁文件被误判为"仍存活"而永不回收到期。对 PID 1 特殊处理：直接按时间判定（超时即 stale）。
    if pid <= 1:
        return True
    try:
        os.kill(pid, 0)
        return False
    except ProcessLookupError:
        return True
    except PermissionError:
        return False


async def _acquire_edit_mutex(key: str, timeout: float | None = None) -> str | None:
    """跨进程拿图生图互斥锁，返回持有 token；拿不到（超时）返回 None。"""
    if not config.EDIT_MUTEX_ENABLED:
        return "noop"
    os.makedirs(_EDIT_MUTEX_DIR, exist_ok=True)
    path = _edit_mutex_path(key)
    deadline = time.monotonic() + timeout if timeout is not None else None
    while True:
        if deadline is not None and time.monotonic() > deadline:
            return None
        try:
            token = uuid.uuid4().hex
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {time.time()} {token}".encode("utf-8"))
            os.close(fd)
            return token
        except FileExistsError:
            if _edit_mutex_stale(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass
                continue
            await asyncio.sleep(1.0)


def _release_edit_mutex(key: str, token: str | None) -> None:
    """释放跨进程锁。仅当锁文件仍属于自己（token 匹配）时删除，防误删他人新锁。"""
    if not config.EDIT_MUTEX_ENABLED or not token or token == "noop":
        return
    path = _edit_mutex_path(key)
    try:
        with open(path, encoding="utf-8") as f:
            parts = f.read().split()
        if len(parts) >= 3 and parts[2] == token:
            os.unlink(path)
    except OSError:
        pass


# ── 图生图跨进程互斥（可切换：SQLite 租约锁 or 文件锁）──
async def _acquire_edit_lock(key: str, holder: str, timeout: float | None = None) -> str | None:
    """按配置选择：租约锁 或 文件锁。返回持有 token；获取失败返回 None。"""
    if config.EDIT_LEASE_ENABLED:
        deadline = time.monotonic() + timeout if timeout is not None else None
        token = uuid.uuid4().hex
        while True:
            if deadline is not None and time.monotonic() > deadline:
                return None
            ok = await _EDIT_LEASE_STORE.acquire(key, holder, token, config.EDIT_LEASE_TTL)
            if ok:
                return token
            await asyncio.sleep(1.0)
    # 兼容旧文件锁
    return await _acquire_edit_mutex(key, timeout)


async def _renew_edit_lock_loop(key: str, token: str) -> asyncio.Task:
    """持锁期间的心跳续租协程。"""
    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(config.EDIT_LEASE_TTL / 3.0)
            try:
                ok = await _EDIT_LEASE_STORE.renew(key, token, config.EDIT_LEASE_TTL)
            except Exception as e:
                log.error("租约锁续租异常 key=%s: %s", key, e)
                continue  # 数据库抖动，继续重试
            if not ok:
                log.warning("租约锁已易主/过期，停止续租 key=%s", key)
                return  # 锁已被抢/释放，停止续租
    t = asyncio.create_task(_heartbeat())
    t.add_done_callback(lambda _: None)  # 回收 unhandled exception 告警
    return t


async def _release_edit_lock(key: str, token: str | None) -> None:
    if config.EDIT_LEASE_ENABLED and token:
        await _EDIT_LEASE_STORE.release(key, token)
    else:
        _release_edit_mutex(key, token)


# ── 图生图住宅代理池 ──
class _EditProxyPool:
    """图生图住宅代理池：分配独立出口 IP 会话，per-代理串行锁。"""

    def __init__(self) -> None:
        self.proxies: list[str] = []
        self._locks: dict[str, asyncio.Lock] = {}
        self._idx = 0
        self.sem_inflight = asyncio.Semaphore(config.IF_EDIT_PROXY_MAX_INFLIGHT)
        if config.EDIT_PROXY_FILE:
            try:
                with open(config.EDIT_PROXY_FILE, encoding="utf-8") as f:
                    self.proxies = [l.strip() for l in f if l.strip() and not l.startswith("#")]
                log.info("图生图代理池加载 %d 个代理（并发上限 %d）",
                         len(self.proxies), config.EDIT_PROXY_PARALLEL)
            except OSError as e:
                log.warning("代理池文件不可读 %s: %s", config.EDIT_PROXY_FILE, e)

    @property
    def enabled(self) -> bool:
        return bool(self.proxies) and config.EDIT_PROXY_PARALLEL > 1

    async def acquire_proxy(self) -> str | None:
        if not self.enabled:
            return None
        await self.sem_inflight.acquire()
        self._idx = (self._idx + 1) % len(self.proxies)
        return self.proxies[self._idx]

    def release_proxy(self, proxy: str | None) -> None:
        if proxy is None:
            return
        self.sem_inflight.release()

    def lock_for(self, proxy: str) -> asyncio.Lock:
        if proxy not in self._locks:
            self._locks[proxy] = asyncio.Lock()
        return self._locks[proxy]


_EDIT_PROXY_POOL = _EditProxyPool()
_EDIT_LEASE_STORE = LeaseStore(os.path.join(os.path.dirname(config.DB_FILE) or ".", "edit_leases.db"))


# ── 图生图路由 ──
async def _dispatch_edit(model: str, prompt: str, image_bytes: bytes, download: bool) -> str:
    """图生图路由：imagefree 走既有 edit 链路；其余提供商后台直调。"""
    model = _normalize_model(model)
    if _provider_prefix(model) == "imagefree":
        job_id = str(uuid.uuid4())
        ctype = imagefree_client.detect_mime(image_bytes)
        await db.create_request(job_id, prompt, "1:1", download, "img", "imagefree/default")
        # P0-3: imagefree 图生图 task 加入 _PROVIDER_TASKS 托盘，确保 shutdown 可优雅取消
        t = asyncio.create_task(_run_edit_job(job_id, image_bytes, ctype, prompt, download,
                                          model.split("/", 1)[-1]))
        _PROVIDER_TASKS.add(t)
        t.add_done_callback(_PROVIDER_TASKS.discard)
        return job_id
    provider = registry.provider_for(model)
    if provider is None:
        raise AppError(ErrorCodes.PROVIDER_DOWN, f"provider {_provider_prefix(model)} 暂时不可用，请稍后重试", 429)
    job_id = str(uuid.uuid4())
    await db.create_request(job_id, prompt, "1:1", download, "img", model)
    t0 = time.monotonic()

    async def _run() -> None:
        try:
            async with _provider_sem(provider.prefix):
                res = await provider.generate(model, prompt, "1:1", images=[image_bytes],
                                              resolution="1K", download=download)
            if res.proxy_used:
                await db.update_proxy_used(job_id, res.proxy_used)
            if res.status == "completed":
                await db.mark_finished(job_id, "completed", res.asset_url, None,
                                 time.monotonic() - t0, res.asset_bytes, res.asset_mime)
                registry.record_success(provider.prefix)
                try:
                    registry.adaptive_router.record_result(
                        provider.prefix, (time.monotonic() - t0) * 1000.0, True)
                except Exception:
                    pass
            else:
                await db.mark_finished(job_id, "error", None, res.error or "生成失败",
                                 time.monotonic() - t0)
                try:
                    registry.adaptive_router.record_result(
                        provider.prefix, (time.monotonic() - t0) * 1000.0, False)
                except Exception:
                    pass
        except Exception as e:
            await db.mark_finished(job_id, "error", None, str(e), time.monotonic() - t0)
            try:
                registry.adaptive_router.record_result(
                    provider.prefix, (time.monotonic() - t0) * 1000.0, False)
            except Exception:
                pass
            log.exception("提供商图生图异常 %s", job_id)

    t = asyncio.create_task(_run())
    _PROVIDER_TASKS.add(t)
    t.add_done_callback(_PROVIDER_TASKS.discard)
    return job_id


async def _dispatch_edit_multi(model: str, prompt: str, image_bytes_list: list[bytes], download: bool) -> str:
    """多图图生图路由：直接调 provider（非 imagefree）。"""
    model = _normalize_model(model)
    provider = registry.provider_for(model)
    if provider is None:
        raise AppError(ErrorCodes.PROVIDER_DOWN, f"provider {_provider_prefix(model)} 暂时不可用，请稍后重试", 429)
    job_id = str(uuid.uuid4())
    await db.create_request(job_id, prompt, "1:1", download, "img", model)
    t0 = time.monotonic()

    async def _run() -> None:
        try:
            async with _provider_sem(provider.prefix):
                res = await provider.generate(model, prompt, "1:1", images=image_bytes_list,
                                              resolution="1K", download=download)
            if res.proxy_used:
                await db.update_proxy_used(job_id, res.proxy_used)
            if res.status == "completed":
                await db.mark_finished(job_id, "completed", res.asset_url, None,
                                 time.monotonic() - t0, res.asset_bytes, res.asset_mime)
                registry.record_success(provider.prefix)
                try:
                    registry.adaptive_router.record_result(
                        provider.prefix, (time.monotonic() - t0) * 1000.0, True)
                except Exception:
                    pass
            else:
                await db.mark_finished(job_id, "error", None, res.error or "生成失败",
                                 time.monotonic() - t0)
                try:
                    registry.adaptive_router.record_result(
                        provider.prefix, (time.monotonic() - t0) * 1000.0, False)
                except Exception:
                    pass
        except Exception as e:
            await db.mark_finished(job_id, "error", None, str(e), time.monotonic() - t0)
            try:
                registry.adaptive_router.record_result(
                    provider.prefix, (time.monotonic() - t0) * 1000.0, False)
            except Exception:
                pass
            log.exception("提供商多图图生图异常 %s", job_id)

    t = asyncio.create_task(_run())
    _PROVIDER_TASKS.add(t)
    t.add_done_callback(_PROVIDER_TASKS.discard)
    return job_id


async def edit_image(req: EditRequest):
    """图生图（AI 照片编辑）端点逻辑。"""
    image_bytes_list: list[bytes] = []
    image_bytes: bytes | None = None
    ctype: str = "image/png"

    if req.images:
        image_bytes_list = _parse_input_images(req.images)
        image_bytes = image_bytes_list[0]
    elif req.image:
        data, ctype = _parse_input_image(req.image)
        if data is None:
            # URL 图片：下载字节后必须回填 image_bytes/image_bytes_list，否则后续全部用 None 提交
            data = await imagefree_client.download_image(req.image, 60.0, config.MAX_IMAGE_BYTES)
            ctype = imagefree_client.detect_mime(data)
            image_bytes = data
            image_bytes_list = [data]
        else:
            detected = imagefree_client.detect_mime(data)
            if detected != "application/octet-stream":
                ctype = detected
            image_bytes = data
            image_bytes_list = [data]
    else:
        raise AppError(ErrorCodes.BAD_REQUEST, "请提供至少一张图片（image 或 images 字段）", 422)

    if image_bytes and imagefree_client.detect_mime(image_bytes) == "application/octet-stream":
        raise AppError(ErrorCodes.BAD_REQUEST, "无法识别的图片格式（支持 PNG/JPEG/WebP/AVIF/GIF）", 422)
    _validate_model(req.model, "img2img")

    if len(image_bytes_list) > 1:
        model = _normalize_model(req.model)
        if _provider_prefix(model) == "imagefree":
            # P0-4: imagefree 上游只支持单图 → 明确报错，不静默丢弃额外图
            raise AppError(
                ErrorCodes.BAD_REQUEST,
                "imagefree 上游仅支持单图参考（多图请使用 aifreeforever / nanobanana）",
                422,
            )

    if len(image_bytes_list) <= 1:
        image_bytes = image_bytes_list[0] if image_bytes_list else image_bytes
        job_id = await _dispatch_edit(req.model, req.prompt, image_bytes, req.download)
    else:
        job_id = await _dispatch_edit_multi(req.model, req.prompt, image_bytes_list, req.download)
    return TaskInfo(**task_to_public(await db.get_public(job_id)))


# ── 图生图后台执行链 ──
async def _run_edit_job(job_id: str, image: bytes, ctype: str, prompt: str,
                        download: bool, model: str = "default") -> None:
    """后台执行图生图全链路，双层互斥保证不撞上游并发=1。"""
    _EDIT_PENDING.add(job_id)
    holder = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
    try:
        proxy = await _EDIT_PROXY_POOL.acquire_proxy()
        key = proxy or "default"
        local_lock = _EDIT_PROXY_POOL.lock_for(key) if proxy else _EDIT_LOCK
        async with local_lock:
            token = await _acquire_edit_lock(key, holder, config.EDIT_CONCURRENCY_WAIT)
            if not token:
                await db.mark_finished(job_id, "error", None,
                                 "图生图繁忙：其他实例正在生成同一出口通道，请稍后重试", None)
                return
            heartbeat = None
            if config.EDIT_LEASE_ENABLED:
                heartbeat = await _renew_edit_lock_loop(key, token)
            try:
                await _run_edit_chain(job_id, image, ctype, prompt, download, model, proxy)
            finally:
                if heartbeat:
                    heartbeat.cancel()
                    try:
                        await heartbeat
                    except asyncio.CancelledError:
                        pass
                await _release_edit_lock(key, token)
    finally:
        _EDIT_PROXY_POOL.release_proxy(proxy)
        _EDIT_PENDING.discard(job_id)


def _is_edit_slot_wedged(err: object) -> bool:
    """上游并发槽被占的判定。"""
    msg = str(err).lower()
    return "already have an image editing task" in msg or "task in progress" in msg


async def _run_edit_chain(job_id: str, image: bytes, ctype: str, prompt: str,
                          download: bool, model: str = "default",
                          proxy: str | None = None) -> None:
    """真正执行图生图提交（持锁后调用）。"""
    t0 = time.monotonic()
    last_err: str | None = None
    for attempt in range(1, config.EDIT_RETRY_MAX + 1):
        token = await engine.acquire_token(key=proxy or "direct")
        if not token:
            await db.mark_finished(job_id, "error", None,
                             "人机验证 token 暂不可用（cf_solver 不可用或熔断中），请稍后重试",
                             time.monotonic() - t0)
            return
        try:
            public_url = await imagefree_client.upload_edit_image(
                config.BASE_URL, image, ctype, proxy=proxy)
            tid = await imagefree_client.submit_edit(
                config.BASE_URL, public_url, config.apply_model(prompt, model), token,
                proxy=proxy)
            await db.update_upstream_task(job_id, tid)
            result = await imagefree_client.poll_edit_status(
                config.BASE_URL, tid, config.EDIT_TIMEOUT, config.GENERATE_POLL_INTERVAL,
                proxy=proxy)
            break
        except Exception as e:
            last_err = str(e)
            if _is_edit_slot_wedged(e) and attempt < config.EDIT_RETRY_MAX:
                log.warning("job %s 上游并发槽被占（第 %d/%d 次），等待 %ds 自愈重试",
                            job_id, attempt, config.EDIT_RETRY_MAX,
                            config.EDIT_RETRY_INTERVAL)
                await asyncio.sleep(config.EDIT_RETRY_INTERVAL)
                continue
            if _is_edit_slot_wedged(e):
                await db.mark_finished(job_id, "error", None,
                                 f"图生图失败（重试 {config.EDIT_RETRY_MAX} 次仍被上游占用）: {e}",
                                 time.monotonic() - t0)
            else:
                await db.mark_finished(job_id, "error", None, f"图生图失败: {e}",
                                 time.monotonic() - t0)
            return
    else:
        await db.mark_finished(job_id, "error", None,
                         f"图生图失败（重试 {config.EDIT_RETRY_MAX} 次仍被上游占用）: {last_err}",
                         time.monotonic() - t0)
        return
    if not download:
        await db.mark_finished(job_id, "completed", result["image"], None, time.monotonic() - t0)
        return
    try:
        raw = await imagefree_client.download_image(result["image"], 60.0, config.MAX_IMAGE_BYTES)
        mime = imagefree_client.detect_mime(raw)
        await db.mark_finished(job_id, "completed", result["image"], None, time.monotonic() - t0,
                         imagefree_client.to_base64(raw, mime), mime)
    except Exception as e:
        log.warning("图生图结果下载失败（不影响 URL 交付）: %s", e)
        await db.mark_finished(job_id, "completed", result["image"], None, time.monotonic() - t0)