"""后端核心调度层（v4.2：从 main.py 迁移的关键逻辑，供 routes/ 复用）。

包含：model 校验/归一化、图生图输入解析、路由分发（_dispatch_*）、
图生图跨进程互斥与代理池、全局 SSE 广播 /v1/events/tasks（向后兼容）。
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import logging
import re
import socket
import time
import uuid
from urllib.parse import urlsplit

from fastapi.responses import StreamingResponse

from . import config
from .models import GenerateRequest
from .meta import db, engine, registry
from .errors import AppError, ErrorCodes
from .semaphore_manager import upstream_semaphore
from .sse_events import publish_task_event
from .worker import QueueFull  # noqa: F401  (generate.py 依赖 dispatch 再导出)

log = logging.getLogger("dispatch")


# ── Model 校验 / 归一化 ──
def _normalize_model(model: str) -> str:
    """旧版风格预设 id（default/anime/...）映射为 imagefree/<id>，向后兼容。"""
    model = model or "default"
    if "/" in model:
        return model
    return f"imagefree/{model}"


def _provider_prefix(model: str) -> str:
    return model.split("/", 1)[0]


def _validate_model(model: str, kind: str = "txt2img") -> None:
    """校验 model 存在且适用于该任务类型。"""
    model = _normalize_model(model)
    spec = registry.model(model)
    if spec is None:
        raise AppError(ErrorCodes.INVALID_MODEL, f"未知 model: {model}，可选见 GET /v1/models", 422)
    cap_map = {"txt2img": "txt2img", "img2img": "img2img", "txt2vid": "txt2vid"}
    cap = cap_map.get(kind)
    if cap is None:
        raise AppError(ErrorCodes.BAD_REQUEST, f"不支持的生成类型: {kind}", 422)
    if cap not in spec.capabilities:
        raise AppError(ErrorCodes.INVALID_MODEL, f"model {model} 不支持 {kind}，仅支持 {list(spec.capabilities)}", 422)


def _validate_ratio(ratio: str) -> None:
    """比例校验：仅格式校验。"""
    if not re.fullmatch(r"\d+:\d+", ratio):
        raise AppError(ErrorCodes.INVALID_RATIO, f"不支持的 aspect_ratio: {ratio}（格式需 N:N，如 1:1、16:9）", 422)


# ── 图生图输入解析 ──
def _parse_input_image(image: str) -> tuple[bytes | None, str | None]:
    """解析图生图输入为 (bytes, content_type)。含 SSRF 防护。"""
    if image.startswith("data:"):
        m = re.match(r"data:([^;,]+);base64,(.*)", image, re.S)
        if not m:
            raise AppError(ErrorCodes.BAD_REQUEST, "data URI 格式错误（需 data:image/*;base64,...）", 422)
        ctype, b64 = m.group(1), m.group(2)
        try:
            data = base64.b64decode(b64)
        except Exception:
            raise AppError(ErrorCodes.BAD_REQUEST, "base64 解码失败", 422)
        if len(data) > config.MAX_IMAGE_BYTES:
            raise AppError(ErrorCodes.BAD_REQUEST, f"图片超过 {config.MAX_IMAGE_BYTES // 1024 // 1024}MB 上限", 413)
        return data, ctype

    if image.startswith("http://") or image.startswith("https://"):
        host = urlsplit(image).hostname
        if not host:
            raise AppError(ErrorCodes.BAD_REQUEST, "图片 URL 无效", 422)
        try:
            results = socket.getaddrinfo(host, 0, proto=socket.IPPROTO_TCP)
        except OSError:
            raise AppError(ErrorCodes.BAD_REQUEST, "图片 URL 无法解析", 422)
        for i in results:
            a = ipaddress.ip_address(i[4][0])
            if a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast:
                raise AppError(ErrorCodes.BAD_REQUEST, "不允许访问内网/本地/保留地址的图片", 400)
        return None, image

    raise AppError(ErrorCodes.BAD_REQUEST, "image 需为 data URI 或 http(s) URL", 422)


def _parse_input_images(images: list[str]) -> list[bytes]:
    """解析多图输入（最多 3 张），返回 bytes 列表。"""
    if not images:
        return []
    if len(images) > 3:
        raise AppError(ErrorCodes.BAD_REQUEST, "参考图最多 3 张", 422)
    result = []
    for i, img in enumerate(images):
        if not img.startswith("data:"):
            raise AppError(ErrorCodes.BAD_REQUEST, f"images[{i}] 需为 data URI 格式", 422)
        m = re.match(r"data:([^;,]+);base64,(.*)", img, re.S)
        if not m:
            raise AppError(ErrorCodes.BAD_REQUEST, f"images[{i}] data URI 格式错误（需 data:image/*;base64,...）", 422)
        try:
            data = base64.b64decode(m.group(2))
        except Exception:
            raise AppError(ErrorCodes.BAD_REQUEST, f"images[{i}] base64 解码失败", 422)
        if len(data) > config.MAX_IMAGE_BYTES:
            raise AppError(ErrorCodes.BAD_REQUEST, f"images[{i}] 图片超过 {config.MAX_IMAGE_BYTES // 1024 // 1024}MB 上限", 413)
        result.append(data)
    return result


# ── 全局 SSE 广播（向后兼容 /v1/events/tasks）──
_SSE_SUBSCRIBERS: set[asyncio.Queue] = set()
_SSE_LOCK = asyncio.Lock()  # P0-1: 保护订阅者集合的并发安全


async def broadcast_task_event(task_id: str, status: str, data: dict | None = None) -> None:
    """向所有在线 SSE 客户端主动推送任务状态变迁（全局广播兼容层）。

    注意：_finish（worker.py）不再调用 publish_task_event，避免双重发布。
    """
    payload = json.dumps({"task_id": task_id, "status": status, "data": data or {}, "ts": time.time()})
    msg = f"event: task_update\ndata: {payload}\n\n"
    # P2-1: 快照与 discard 均在 _SSE_LOCK 内，消除极端竞态
    async with _SSE_LOCK:
        subs = list(_SSE_SUBSCRIBERS)
        for q in subs:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                # 队列满 → 移除该慢客户端，不阻塞广播
                _SSE_SUBSCRIBERS.discard(q)
            except Exception:
                pass
    # v4.2: 同时发布到 per-task 事件流（仅发布一次，非双重）
    try:
        publish_task_event(task_id, "result" if status == "completed" else "error",
                           {"task_id": task_id, "status": status, ** (data or {})})
    except Exception:
        pass


async def sse_task_events():
    """全局 SSE（向后兼容）：所有任务状态广播。"""
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    async with _SSE_LOCK:
        _SSE_SUBSCRIBERS.add(q)

    async def event_generator():
        try:
            yield "event: connected\ndata: {\"status\":\"ready\"}\n\n"
            while True:
                msg = await q.get()
                yield msg
        except asyncio.CancelledError:
            pass
        finally:
            async with _SSE_LOCK:
                _SSE_SUBSCRIBERS.discard(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── 多提供商路由 ──
_PROVIDER_TASKS: set[asyncio.Task] = set()  # 持有 provider 后台任务引用，防 GC
_provider_semaphores: dict[tuple[int, str, int], asyncio.Semaphore] = {}
# P1-D: 非 imagefree 提供商按优先级并发控制。P0 立即执行（不排队）、P1 有限并发、P2 串行排队。
# _provider_workers 缓存每 (provider_prefix, priority) 的消费者任务；信号量由 _provider_sem(prefix, limit) 提供：
#   P0 → 无限并发（不经过信号量）、P1 → 每提供商 4 个并发、P2 → 每提供商 1 个（串行 FIFO）。
_ADMIN_PRIORITY = 0
_HIGH_PRIORITY = 1
_NORMAL_PRIORITY = 2
# P1 与 P2 的并发上限（供 _dispatch_generate 创建对应信号量 adapter）
_HIGH_CONCURRENCY = 4
_NORMAL_CONCURRENCY = 1


def _provider_sem(prefix: str, limit: int = 16) -> asyncio.Semaphore:
    """按 (event_loop, prefix, limit) 缓存信号量——不同 limit 视为不同信号量，
    供优先级队列复用（P1=4, P2=1, 编辑=16 等各独立）。"""
    key = (id(asyncio.get_running_loop()), prefix, limit)
    if key not in _provider_semaphores:
        _provider_semaphores[key] = asyncio.Semaphore(limit)
    return _provider_semaphores[key]


async def _dispatch_generate(req: GenerateRequest) -> str:
    """按 model 前缀路由：imagefree 走既有引擎队列；其余提供商后台直调。

    v4.2：imagefree 主路径也走 registry.provider_for() 记录路由（全覆盖），
    但若返回的仍是 imagefree 则进引擎队列（保持既有高性能路径）。
    """
    from .config import IF_IDEMPOTENCY_ENABLED
    idempotency_key = getattr(req, "idempotency_key", None)
    if IF_IDEMPOTENCY_ENABLED and idempotency_key:
        existing = await db.get_idempotency(idempotency_key)
        if existing is not None:
            log.info("幂等提交命中: key=%s task_id=%s", idempotency_key, existing["task_id"])
            return existing["task_id"]

    model = _normalize_model(req.model)
    # 路由记录全覆盖：先经 registry（含 imagefree），失败再回退原路径
    provider = None
    try:
        provider = registry.provider_for(model)
    except Exception as e:
        log.warning("路由决策异常，回退默认路径: %s", e)

    # P0-6: priority=0 是 admin 级别，不可用 or 2 判定
    priority = req.priority if req.priority is not None else 2

    if provider is None or provider.prefix == "imagefree":
        # imagefree 主路径：走既有引擎队列（高性能）
        task_id = await engine.submit_priority(req.prompt, req.aspect_ratio, req.download,
                                               model.split("/", 1)[-1],
                                               priority=priority,
                                               client_ip=getattr(req, "client_ip", None),
                                               user_agent=getattr(req, "user_agent", None))
        # 路由记录：imagefree 请求也写入（记录请求最终由 imagefree/engine 处理）
        try:
            registry.adaptive_router.record_result("imagefree", 0.0, True)
        except Exception:
            pass
        if IF_IDEMPOTENCY_ENABLED and idempotency_key:
            await db.save_idempotency(idempotency_key, task_id)
        return task_id

    if provider is None:
        raise AppError(ErrorCodes.PROVIDER_DOWN, f"provider {_provider_prefix(model)} 暂时不可用，请稍后重试", 429)

    task_id = str(uuid.uuid4())
    await db.create_request(task_id, req.prompt, req.aspect_ratio, req.download, "txt", model,
                            client_ip=getattr(req, "client_ip", None),
                            user_agent=getattr(req, "user_agent", None))
    t0 = time.monotonic()
    spec = registry.model(model)

    if IF_IDEMPOTENCY_ENABLED and idempotency_key:
        await db.save_idempotency(idempotency_key, task_id)

    async def _run() -> None:
        # P1-D: 非 imagefree 路径按 priority 控制并发
        # P0 → 无限并发（不经过信号量，立即执行）
        # P1 → 有限并发（每提供商 4 个）
        # P2 → 串行 FIFO 排队（每提供商 1 个）
        if priority == _ADMIN_PRIORITY:
            sem = None
        elif priority == _HIGH_PRIORITY:
            sem = _provider_sem(provider.prefix, _HIGH_CONCURRENCY)
        else:
            sem = _provider_sem(provider.prefix, _NORMAL_CONCURRENCY)
        try:
            if sem:
                await sem.acquire()
            async with upstream_semaphore:
                res = await provider.generate(
                    model, req.prompt, req.aspect_ratio, images=None,
                    resolution=req.resolution, download=req.download,
                    duration=req.duration or (spec.meta.get("video_durations") or [4])[0],
                )
            if res.proxy_used:
                await db.update_proxy_used(task_id, res.proxy_used)
            if res.status == "completed":
                await db.mark_finished(task_id, "completed", res.asset_url, None,
                                 time.monotonic() - t0, res.asset_bytes, res.asset_mime)
                registry.record_success(provider.prefix)
                try:
                    registry.adaptive_router.record_result(
                        provider.prefix, (time.monotonic() - t0) * 1000.0, True)
                except Exception:
                    pass
            else:
                await db.mark_finished(task_id, "error", None, res.error or "生成失败",
                                 time.monotonic() - t0)
                try:
                    registry.adaptive_router.record_result(
                        provider.prefix, (time.monotonic() - t0) * 1000.0, False)
                except Exception:
                    pass
        except Exception as e:
            await db.mark_finished(task_id, "error", None, str(e), time.monotonic() - t0)
            try:
                registry.adaptive_router.record_result(
                    provider.prefix, (time.monotonic() - t0) * 1000.0, False)
            except Exception:
                pass
            log.exception("提供商生成异常 %s", task_id)
        finally:
            if sem:
                sem.release()

    t = asyncio.create_task(_run())
    _PROVIDER_TASKS.add(t)
    t.add_done_callback(_PROVIDER_TASKS.discard)
    return task_id


# ── 图生图编辑路由（保持 main.py 原有逻辑镜像）──
# 注意：不在 dispatch.py 尾部 import dispatch_edit（会产生循环引用）。
# dispatch_edit 只从 dispatch 导入工具函数，不从 dispatch 导入 _dispatch 模块。
# routes/generate.py 直接用 dispatch_edit.edit_image。