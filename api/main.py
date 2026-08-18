"""imagefree_api 主服务：把 imagefree.net 图像生成封装为可调用的 HTTP API。

高并发架构：请求只做 校验→入库→入队→返回（毫秒级），可扛 50 RPS 入口；
后台 worker 池 + Turnstile token 预取池消费队列，异步出图。
首页 `GET /` 为对外中文 API 文档（含用量统计、实时并发、作品画廊）。
"""
import asyncio
import base64
import hashlib
import hmac
import ipaddress
import logging
import os
import re
import socket
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from .errors import AppError, ErrorCodes, error_response, STATUS_CODE_ERROR_MAP
from pydantic import BaseModel, Field

# A-05: contextvars 请求上下文
from .context import RequestContextMiddleware, RequestIdLogFilter

from . import config
from . import imagefree_client
from . import turnstile_client
from .base64_store import ensure_dir as ensure_base64_dir
from .log_buffer import log_buffer as log_buffer_handler
from .db import DB, task_to_public
from .solver_guard import REASON_CATEGORIES, solver_guard
from .worker import Engine, QueueFull
from .cache import LRUCache
from .cache_warmup import warmup_cache
from .telemetry import init_telemetry, shutdown_telemetry
from .audit import audit_log
from .providers import registry
from .providers.registry import bootstrap as providers_bootstrap
from .providers.registry import startup_all as providers_startup
from .providers.registry import shutdown_all as providers_shutdown

# M3: 结构化日志格式（含 trace_id 占位，日志里以 trace=<id> 呈现）。
# IMP-08: trace_id 由 LoggingInstrumentor + TraceIdLogFilter 动态追加到 message 末尾，
# 不再需要占位符；保持格式不变以兼容旧有日志解析。
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT,
                    datefmt="%Y-%m-%d %H:%M:%S")
# 注入 LogBuffer 到 root logger，捕获所有模块的日志
logging.getLogger().addHandler(log_buffer_handler)
# A-05: 注入 RequestIdLogFilter，自动在日志消息末尾追加 [req=<request_id>]
logging.getLogger().addFilter(RequestIdLogFilter())

log = logging.getLogger("imagefree_api")


def _uptime_human(seconds: int) -> str:
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}天{h}小时"
    if h:
        return f"{h}小时{m}分钟"
    if m:
        return f"{m}分钟"
    return f"{seconds}秒"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # IMP-08: 启动 OTel 追踪（IF_OTEL_ENABLED=1 时生效）
    init_telemetry()
    await engine.start()
    gallery_cache.start_reaper()
    # IMP-11: 启动时从 DB 恢复缓存
    restored = await gallery_cache.restore_from_db()
    if restored:
        log.info("缓存从 DB 恢复完成: %d 个条目", restored)
    # F-05: 启动时预热常见查询缓存（异步，不影响启动速度）
    _warmup_task = asyncio.create_task(warmup_cache(gallery_cache, db))
    # IMP-25: 启动 DB 批量写入定时器
    _batch_timer_task = None
    if config.IF_DB_BATCH_ENABLED:
        _batch_timer_task = asyncio.create_task(db.start_batch_timer())
    # 多提供商网关：注册 provider 实例 + 启动号池/注册器/代理池
    providers_bootstrap()
    imagefree_provider = registry.providers.get("imagefree")
    if imagefree_provider:
        imagefree_provider.engine = engine
    from .proxy_pool import proxy_pool
    if config.PROXY_FILE:
        proxy_pool.load_file(config.PROXY_FILE)
    aifree = registry.providers.get("aifreeforever")
    if aifree:
        aifree._proxy_pool = proxy_pool
    # 免费代理抓取循环（低成本轮换；IF_FREE_PROXY=1 开启）
    from .free_proxy_fetcher import free_proxy_fetcher
    await free_proxy_fetcher.start()
    # 号池 + 注册器 + 签到
    if config.ACCOUNT_AUTO:
        from . import registerer
        from .account_pool import account_pool
        account_pool.registerers.update(registerer.build_registerers())
        await account_pool.start()
    await providers_startup()
    # IMP-26: 启动时确保 base64 缓存目录存在
    ensure_base64_dir()
    # 启动时清理一次过期 base64 文件
    try:
        n = db.clean_base64_files(config.IF_BASE64_FILE_TTL)
        if n:
            log.info("base64 文件启动清理: 删除 %d 个过期文件", n)
    except Exception as e:
        log.warning("base64 文件启动清理失败（可忽略）: %s", e)
    # M7: 启动时清理一次超期记录（防长时间离线后表膨胀）。
    # H1(审计): cleanup 含 VACUUM 同步阻塞，放入线程池避免冻结事件循环。
    try:
        r = await asyncio.to_thread(db.cleanup, config.DB_RETENTION_DAYS)
        log.info("DB 启动清理: %s", r)
    except Exception as e:
        log.warning("DB 启动清理失败（可忽略）: %s", e)
    # M7: 周期性清理任务
    async def _cleanup_loop() -> None:
        while True:
            try:
                await asyncio.sleep(config.DB_CLEANUP_INTERVAL)
                r = await asyncio.to_thread(db.cleanup, config.DB_RETENTION_DAYS)
                log.info("DB 周期清理: %s", r)
                # IMP-26: 周期性清理过期 base64 文件
                n = db.clean_base64_files(config.IF_BASE64_FILE_TTL)
                if n:
                    log.info("base64 文件周期清理: 删除 %d 个过期文件", n)
                # IMP-06: 周期性清理过期幂等 key
                if config.IF_IDEMPOTENCY_ENABLED:
                    nd = db.clean_expired_idempotency()
                    if nd:
                        log.info("幂等 key 周期清理: 删除 %d 个过期条目", nd)
                # 死信队列过期清理
                if config.IF_DLQ_ENABLED:
                    ndlq = db.clean_expired_dlq()
                    if ndlq:
                        log.info("死信队列周期清理: 删除 %d 个过期条目", ndlq)
                # 缓存表过期清理
                nc = db.clean_expired_cache()
                if nc:
                    log.info("缓存表周期清理: 删除 %d 个过期条目", nc)
                # 持久化队列清理（超期 completed/processing）
                if config.IF_PERSISTENT_QUEUE_ENABLED and engine._queue_db:
                    nq = engine._queue_db.cleanup()
                    if nq.get("deleted"):
                        log.info("持久化队列周期清理: 删除 %d 个过期条目", nq["deleted"])
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("DB 周期清理失败: %s", e)
    cleanup_task = asyncio.create_task(_cleanup_loop())

    # IMP-22: 上游健康探测循环
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
    _health_task = None
    if config.IF_HEALTH_CHECK_ENABLED:
        _health_task = asyncio.create_task(_health_check_loop(interval=config.IF_HEALTH_CHECK_INTERVAL))

    # IMP-18: provider 降级恢复探测循环
    async def _provider_recover_loop() -> None:
        while True:
            try:
                await asyncio.sleep(config.IF_PROVIDER_RECOVER_INTERVAL)
                registry.try_recover_all()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("provider 恢复探测循环异常: %s", e)
    _recover_task = asyncio.create_task(_provider_recover_loop())

    yield
    # F-05: 停止缓存预热任务
    if _warmup_task and not _warmup_task.done():
        _warmup_task.cancel()
        try:
            await _warmup_task
        except asyncio.CancelledError:
            pass
    # IMP-25: 停止前刷新 DB 写缓冲区
    if _batch_timer_task:
        _batch_timer_task.cancel()
        try:
            await _batch_timer_task
        except asyncio.CancelledError:
            pass
    db.flush()  # 确保缓冲区数据不丢
    cleanup_task.cancel()
    # IMP-22: 停止健康探测循环
    if _health_task:
        _health_task.cancel()
        try:
            await _health_task
        except asyncio.CancelledError:
            pass
    # IMP-18: 停止 provider 恢复探测循环
    _recover_task.cancel()
    try:
        await _recover_task
    except asyncio.CancelledError:
        pass
    await providers_shutdown()
    from .free_proxy_fetcher import free_proxy_fetcher
    await free_proxy_fetcher.stop()
    from .account_pool import account_pool
    await account_pool.stop()
    # IMP-11: 停止前 flush 缓存持久化
    gallery_cache.flush_to_db()
    await gallery_cache.stop_reaper()
    await engine.stop()
    # H2: 服务停止时关闭共享 HTTP 连接池
    await turnstile_client.close_client()
    await imagefree_client.close_client()
    # IMP-08: 关闭 OTel 追踪（Flush + 反注册 Instrumentation）
    shutdown_telemetry()


db = DB(config.DB_FILE)
engine = Engine(db)
gallery_cache = LRUCache(maxsize=config.IF_LRU_CACHE_SIZE, ttl=config.IF_LRU_CACHE_TTL,
                          persist_db=db)

app = FastAPI(
    title="imagefree API",
    version="2.2.0",
    description="AI 图像生成开放接口：自动完成 Cloudflare Turnstile 人机验证，无感调用。"
                "高并发异步队列，文档见首页 GET /，Swagger 见 /docs。",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
# A-05: contextvars 请求上下文中间件 - 在每个请求开始时设置 request context
app.add_middleware(RequestContextMiddleware)

# ── 统一错误处理 ─────────────────────────────────
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    """AppError → 统一错误响应格式。"""
    return error_response(exc.code, exc.message, exc.status_code, exc.details)


@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    """HTTPException → 统一错误响应格式（状态码/SQL/业务），映射到标准错误码。"""
    _status_code = exc.status_code
    _message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return error_response(
        STATUS_CODE_ERROR_MAP.get(_status_code, ErrorCodes.BAD_REQUEST),
        _message,
        _status_code,
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """未捕获的异常 → 500（避免栈溢出到客户端）。"""
    log.exception("未捕获的异常: %s", exc)
    return error_response(
        ErrorCodes.INTERNAL_ERROR,
        "服务器内部错误",
        status_code=500,
    )

_DOCS_PAGE = Path(__file__).parent / "docs.html"


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=config.MAX_PROMPT_LEN)
    aspect_ratio: str = Field("1:1", pattern=r"^\d+:\d+$")
    download: bool = Field(False, description="是否同时下载图片并返回 base64")
    model: str = Field("imagefree/default",
                       description="模型 id，见 GET /v1/models（格式：<提供商>/<真实模型名>，如 minimaxh3/nano-banana-pro）")
    resolution: str = Field("1K", description="分辨率：1K/2K/4K 或视频 480p/720p")
    duration: int | None = Field(None, ge=4, le=15,
                                  description="视频时长秒数：4/8/12/15")
    priority: int | None = Field(None, ge=0, le=2,
                                  description="优先级：0=admin, 1=paid, 2=normal；不传默认 normal")
    idempotency_key: str | None = Field(None, max_length=128,
                                         description="幂等 key：同一 key 重复提交返回相同 task_id（IF_IDEMPOTENCY_ENABLED=1 时生效）")


class EditRequest(BaseModel):
    """图生图（AI 照片编辑）：输入一张图（或最多 3 张参考图）+ 提示词 → 生成变体。"""
    image: str = Field("", description="输入图（单张，向后兼容）：data URI（image/png 等;base64）或公开 http(s) 图片 URL")
    images: list[str] = Field([], description="输入图数组（最多 3 张）：data URI 数组，每项格式 data:image/*;base64,...")
    prompt: str = Field(..., min_length=1, max_length=config.MAX_PROMPT_LEN,
                        description="编辑指令，例如：make it a watercolor painting")
    download: bool = Field(False, description="完成后是否同时下载结果图并返回 base64")
    model: str = Field("imagefree/default", description="模型 id，见 GET /v1/models（图生图能力模型）")


# 图生图全局串行锁：上游 ai-photo-editor 硬并发=1（同出口 IP 只能 1 个编辑任务在途，实测确认），
# 故所有编辑任务必须串行提交，避免撞上游 429/400 "task in progress"。
# 双层互斥：
#   1) 进程内 asyncio.Lock（快速路径，同进程任务严格排队）
#   2) 跨进程文件锁（O_EXCL 原子创建，data 卷内可见）→ 多进程/多实例部署也不撞上游。
# _EDIT_PENDING 记录排队中任务（入参已落 DB，进程重启不丢，此集合仅用于排查看板）。
# 若配置住宅代理池（EDIT_PROXY_FILE），则按 per-代理锁：同一代理(出口IP)串行，不同代理并行。
_EDIT_LOCK = asyncio.Lock()
_EDIT_PENDING: set[str] = set()

# ── 跨进程图生图互斥（文件锁）────────────────────────
# 上游并发=1 是全局硬限制，跨进程/多实例也必须串行。用 O_EXCL 文件锁（DB 同目录卷内），
# 进程崩溃后锁文件靠「PID 不存在 或 超时」stale 检测自动清理，不会永久死锁。
_EDIT_MUTEX_DIR = os.path.join(os.path.dirname(config.DB_FILE) or ".", ".edit_locks")


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
        return True  # 文件读不了/损坏 → 视为 stale，可清理
    if time.time() - ts > config.EDIT_LOCK_MAX_AGE:
        return True
    if os.name == "nt":
        # Windows 无 os.kill(pid,0) 替代方案，但时间超时（EDIT_LOCK_MAX_AGE）已在上方判定，
        # 锁文件 mtime 超时后 _acquire_edit_mutex 会竞争中清理，不会永久死锁。
        return False
    try:
        os.kill(pid, 0)
        return False
    except ProcessLookupError:
        return True  # 持有进程已退出 → stale
    except PermissionError:
        return False


async def _acquire_edit_mutex(key: str, timeout: float | None = None) -> str | None:
    """跨进程拿图生图互斥锁，返回持有 token；拿不到（超时）返回 None。

    key: "default"（直连）或代理 URL（per-代理并行时按代理分锁）。
    timeout: None = 无限等待（stale 兜底，符合图生图长排队语义）；测试可传有限值。
    """
    if not config.EDIT_MUTEX_ENABLED:
        return "noop"  # 未启用跨进程锁 → 仅靠进程内 asyncio.Lock
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


class _EditProxyPool:
    """图生图住宅代理池：分配独立出口 IP 会话，per-代理串行锁。

    token 与提交必须同一代理 IP（上游校验），故一个任务全程用分配的代理：
    cf_solver 解 token 传 proxy → upload/submit/poll 全走该 proxy。
    未配置代理文件时返回空，走直连 + 全局锁（单并发，现状）。
    """

    def __init__(self) -> None:
        self.proxies: list[str] = []
        self._locks: dict[str, asyncio.Lock] = {}
        self._idx = 0
        # IMP-19: 图生图代理池并行上限信号量（同一时刻最多 IF_EDIT_PROXY_MAX_INFLIGHT 个代理会话在途）
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
        """async round-robin 分配一个代理；池未启用返回 None（直连）。

        先获取 sem_inflight 信号量限制并发，再 round-robin 分配。
        """
        if not self.enabled:
            return None
        await self.sem_inflight.acquire()
        self._idx = (self._idx + 1) % len(self.proxies)
        return self.proxies[self._idx]

    def release_proxy(self, proxy: str | None) -> None:
        """释放代理占用的信号量槽位。"""
        if proxy is None:
            return
        self.sem_inflight.release()

    def lock_for(self, proxy: str) -> asyncio.Lock:
        """每个代理一个串行锁（同 IP 不能并行，不同 IP 并行）。"""
        if proxy not in self._locks:
            self._locks[proxy] = asyncio.Lock()
        return self._locks[proxy]


_EDIT_PROXY_POOL = _EditProxyPool()


class TaskInfo(BaseModel):
    id: str
    status: str
    image_url: str | None = None
    image_base64: str | None = None
    image_mime: str | None = None
    error: str | None = None
    created_at: float | None = None
    duration_sec: float | None = None
    type: str = "txt"
    model: str = "default"
    prompt: str | None = None
    aspect_ratio: str | None = None


def _validate_model(model: str, kind: str = "txt2img") -> None:
    """校验 model 存在且适用于该任务类型。

    兼容旧版风格预设（"default" → imagefree/default）；新模型命名 "<提供商>/<真实模型>"，
    一律查注册表。kind ∈ txt2img/img2img/txt2vid。
    """
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


def _normalize_model(model: str) -> str:
    """旧版风格预设 id（default/anime/...）映射为 imagefree/<id>，向后兼容。"""
    model = model or "default"
    if "/" in model:
        return model
    return f"imagefree/{model}"


def _validate_ratio(ratio: str) -> None:
    """比例校验：仅格式校验（各提供商按自己的能力面在生成时校验）。"""
    if not re.fullmatch(r"\d+:\d+", ratio):
        raise AppError(ErrorCodes.INVALID_RATIO, f"不支持的 aspect_ratio: {ratio}（格式需 N:N，如 1:1、16:9）", 422)


def _parse_input_image(image: str) -> tuple[bytes | None, str | None]:
    """解析图生图输入为 (bytes, content_type)。

    - data URI → 直接解码出字节与声明类型
    - http(s) URL → 返回 (None, url)，由端点下载；先做 SSRF 防护（拒绝私网/回环）
    """
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
        # SSRF 防护：目标解析到私网/回环/链路本地地址一律拒绝
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
    """解析多图输入（最多 3 张），返回 bytes 列表。

    aifreeforever 支持最多 3 张参考图，minimaxh3 支持多张 base64 直传。
    imagefree 上游只支持 1 张。
    """
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


# ── 端点 ────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def index():
    """对外中文 API 文档首页。"""
    return FileResponse(_DOCS_PAGE, media_type="text/html")


_TERMS_PAGE = Path(__file__).parent / "static" / "terms.html"


@app.get("/v1/terms", include_in_schema=False)
async def terms():
    """服务条款页面。"""
    return FileResponse(_TERMS_PAGE, media_type="text/html")


# M5: cf_solver 探活结果 TTL 缓存（避免每请求建 TCP 连接探测）
_cf_probe_cache: dict = {"ok": False, "at": 0.0}


async def _probe_cf_solver(force: bool = False) -> bool:
    if not force and time.time() - _cf_probe_cache["at"] < config.HEALTHZ_CACHE_TTL:
        return _cf_probe_cache["ok"]
    # L2(审计): 用 urlsplit 解析，避免 split("//")/split(":") 对带路径/尾斜杠/IPv6 URL 崩溃
    try:
        u = urlsplit(config.CF_SOLVER_URL)
        host, port = u.hostname or "127.0.0.1", u.port or 8001
    except (ValueError, IndexError):
        _cf_probe_cache.update(ok=False, at=time.time())
        return False
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, int(port)), timeout=2.0)
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
        except Exception:
            pass
        _cf_probe_cache.update(ok=True, at=time.time())
        return True
    except Exception:
        _cf_probe_cache.update(ok=False, at=time.time())
        return False


@app.get("/v1/healthz")
async def healthz():
    """健康检查：本服务 + cf_solver 可用性 + solver 求解质量（M5：探活 TTL 缓存 + 深指标）。"""
    cf_ok = await _probe_cf_solver()
    snap = engine.snapshot()
    ssnap = solver_guard.snapshot()
    return {
        # solver 熔断 OPEN 或求解质量劣化（degraded）时即使 cf_solver 探活正常也按 degraded 处理
        "status": "degraded" if (not cf_ok or ssnap["solver_status"] != "ok") else "ok",
        "cf_solver": "up" if cf_ok else "down",
        "processing": engine.processing,
        "queued": engine.queue.qsize(),
        "queue_capacity": snap["queue_capacity"],
        "workers": snap["workers"],
        "token_pool": engine.token_pool.qsize(),          # 深指标：token 池水位
        "edit_inflight": len(_EDIT_PENDING),              # 图生图在途/排队任务数（上游硬并发=1）
        "db_rows": db.count(),                             # 深指标：请求记录总量
        "uptime_seconds": snap["uptime_seconds"],
        "timestamp": int(time.time()),
        # ── solver 求解质量（来自 solver_guard.snapshot() 投影）──
        "solver_status": ssnap["solver_status"],           # ok/degraded/circuit_open
        "solve_success_total": ssnap["solve_success_total"],
        "solve_failure_total": ssnap["solve_failure_total"],
        "solve_avg_seconds": ssnap["solve_avg_seconds"],
        "solve_window_success_rate": ssnap["window_success_rate"],
        "solve_window_solve_count": ssnap["window_solve_count"],
        "solve_consecutive_failures": ssnap["consecutive_failures"],
        "solve_last_failure_at": ssnap["last_failure_at"],
        "solver_circuit_open": ssnap["circuit_open"],
        "solve_rejected_total": ssnap["rejected_total"],
        "token_pools": engine.token_pool_manager.pools_snapshot(),  # 各 token 池水位（含 per-proxy 池）
    }


@app.post("/v1/generate", response_model=TaskInfo, summary="生成图片/视频（同步等待）")
async def generate_sync(request: Request, req: GenerateRequest):
    """按 model 路由到对应提供商并同步等待出图/出视频（最长 SYNC_TIMEOUT）。

    model 格式 `<提供商>/<真实模型名>`（如 minimaxh3/nano-banana-pro），见 GET /v1/models。
    语义（H7）：完成或业务失败返回 200（用 status 区分 completed/error）；
    超过等待窗口仍未终态返回 202 + Location 指向任务查询端点。
    """
    _validate_ratio(req.aspect_ratio)
    _validate_model(req.model, "txt2vid" if req.duration else "txt2img")
    try:
        task_id = await _dispatch_generate(req)
    except QueueFull as e:
        raise AppError(ErrorCodes.QUEUE_FULL, str(e), 429)
    task = await engine.wait_result(task_id, config.SYNC_TIMEOUT)
    if task["status"] in ("completed", "error"):
        return TaskInfo(**task_to_public(task))
    body = task_to_public(task)
    body["status"] = "queued"
    body["error"] = "仍在排队/生成中，GET /v1/tasks/{id} 查询"
    return JSONResponse(status_code=202, content=body,
                        headers={"Location": f"{request.base_url}v1/tasks/{task_id}"})


@app.post("/v1/generate/async", response_model=TaskInfo, summary="生成图片/视频（异步，立即返回）")
async def generate_async(req: GenerateRequest):
    """入队立即返回 task_id，用 GET /v1/tasks/{id} 查询结果。高并发推荐此模式。"""
    _validate_ratio(req.aspect_ratio)
    _validate_model(req.model, "txt2vid" if req.duration else "txt2img")
    try:
        task_id = await _dispatch_generate(req)
    except QueueFull as e:
        raise AppError(ErrorCodes.QUEUE_FULL, str(e), 429)
    headers = {"Location": f"/v1/tasks/{task_id}"}
    return TaskInfo(**task_to_public(db.get_public(task_id)))


# ── 多提供商路由 ─────────────────────────────────
_PROVIDER_TASKS: set[asyncio.Task] = set()  # 持有 provider 后台任务引用，防 GC


def _provider_prefix(model: str) -> str:
    return model.split("/", 1)[0]


async def _dispatch_generate(req: GenerateRequest) -> str:
    """按 model 前缀路由：imagefree 走既有引擎队列；其余提供商后台直调。"""
    from .config import IF_IDEMPOTENCY_ENABLED
    if IF_IDEMPOTENCY_ENABLED and req.idempotency_key:
        existing = db.get_idempotency(req.idempotency_key)
        if existing is not None:
            log.info("幂等提交命中: key=%s task_id=%s", req.idempotency_key, existing["task_id"])
            return existing["task_id"]

    model = _normalize_model(req.model)
    if _provider_prefix(model) == "imagefree":
        return await engine.submit_priority(req.prompt, req.aspect_ratio, req.download,
                                           model.split("/", 1)[-1],
                                           priority=req.priority or 2)
    provider = registry.provider_for(model)
    if provider is None:
        raise AppError(ErrorCodes.PROVIDER_DOWN, f"provider {_provider_prefix(model)} 暂时不可用，请稍后重试", 429)
    task_id = str(uuid.uuid4())
    db.create_request(task_id, req.prompt, req.aspect_ratio, req.download, "txt", model)
    t0 = time.monotonic()
    spec = registry.model(model)

    if IF_IDEMPOTENCY_ENABLED and req.idempotency_key:
        db.save_idempotency(req.idempotency_key, task_id)

    async def _run() -> None:
        try:
            res = await provider.generate(
                model, req.prompt, req.aspect_ratio, images=None,
                resolution=req.resolution, download=req.download,
                duration=req.duration or (spec.meta.get("video_durations") or [4])[0],
            )
            if res.proxy_used:
                db.update_proxy_used(task_id, res.proxy_used)
            if res.status == "completed":
                db.mark_finished(task_id, "completed", res.asset_url, None,
                                 time.monotonic() - t0, res.asset_bytes, res.asset_mime)
                registry.record_success(provider.prefix)
            else:
                db.mark_finished(task_id, "error", None, res.error or "生成失败",
                                 time.monotonic() - t0)
        except Exception as e:
            db.mark_finished(task_id, "error", None, str(e), time.monotonic() - t0)
            log.exception("提供商生成异常 %s", task_id)

    t = asyncio.create_task(_run())
    _PROVIDER_TASKS.add(t)
    t.add_done_callback(_PROVIDER_TASKS.discard)
    return task_id


async def _dispatch_edit(model: str, prompt: str, image_bytes: bytes, download: bool) -> str:
    """图生图路由：imagefree 走既有 edit 链路；其余提供商后台直调。"""
    model = _normalize_model(model)
    if _provider_prefix(model) == "imagefree":
        job_id = str(uuid.uuid4())
        ctype = imagefree_client.detect_mime(image_bytes)
        db.create_request(job_id, prompt, "1:1", download, "img", "imagefree/default")
        asyncio.create_task(_run_edit_job(job_id, image_bytes, ctype, prompt, download,
                                          model.split("/", 1)[-1]))  # H2(审计修复): 风格名传递
        return job_id
    provider = registry.provider_for(model)
    if provider is None:
        # IMP-18: provider 熔断/降级不可用 → 返回 429
        raise AppError(ErrorCodes.PROVIDER_DOWN, f"provider {_provider_prefix(model)} 暂时不可用，请稍后重试", 429)
    job_id = str(uuid.uuid4())
    db.create_request(job_id, prompt, "1:1", download, "img", model)
    t0 = time.monotonic()

    async def _run() -> None:
        try:
            res = await provider.generate(model, prompt, "1:1", images=[image_bytes],
                                          resolution="1K", download=download)
            if res.proxy_used:
                db.update_proxy_used(job_id, res.proxy_used)
            if res.status == "completed":
                db.mark_finished(job_id, "completed", res.asset_url, None,
                                 time.monotonic() - t0, res.asset_bytes, res.asset_mime)
                # IMP-18: 生成成功 → 重置连续失败计数
                registry.record_success(provider.prefix)
            else:
                db.mark_finished(job_id, "error", None, res.error or "生成失败",
                                 time.monotonic() - t0)
        except Exception as e:
            db.mark_finished(job_id, "error", None, str(e), time.monotonic() - t0)
            log.exception("提供商图生图异常 %s", job_id)

    t = asyncio.create_task(_run())
    _PROVIDER_TASKS.add(t)
    t.add_done_callback(_PROVIDER_TASKS.discard)
    return job_id


async def _dispatch_edit_multi(model: str, prompt: str, image_bytes_list: list[bytes], download: bool) -> str:
    """多图图生图路由：直接调 provider（非 imagefree，imagefree 只支持单图）。

    aifreeforever 支持最多 3 张参考图，minimaxh3 支持多张 base64 直传。
    """
    model = _normalize_model(model)
    provider = registry.provider_for(model)
    if provider is None:
        raise AppError(ErrorCodes.PROVIDER_DOWN, f"provider {_provider_prefix(model)} 暂时不可用，请稍后重试", 429)
    job_id = str(uuid.uuid4())
    db.create_request(job_id, prompt, "1:1", download, "img", model)
    t0 = time.monotonic()

    async def _run() -> None:
        try:
            res = await provider.generate(model, prompt, "1:1", images=image_bytes_list,
                                          resolution="1K", download=download)
            if res.proxy_used:
                db.update_proxy_used(job_id, res.proxy_used)
            if res.status == "completed":
                db.mark_finished(job_id, "completed", res.asset_url, None,
                                 time.monotonic() - t0, res.asset_bytes, res.asset_mime)
                registry.record_success(provider.prefix)
            else:
                db.mark_finished(job_id, "error", None, res.error or "生成失败",
                                 time.monotonic() - t0)
        except Exception as e:
            db.mark_finished(job_id, "error", None, str(e), time.monotonic() - t0)
            log.exception("提供商多图图生图异常 %s", job_id)

    t = asyncio.create_task(_run())
    _PROVIDER_TASKS.add(t)
    t.add_done_callback(_PROVIDER_TASKS.discard)
    return job_id


@app.post("/v1/edit", response_model=TaskInfo, summary="图生图（AI 照片编辑，异步提交）")
async def edit_image(req: EditRequest):
    """输入一张图（或最多 3 张参考图）+ 编辑指令 → 上游生成变体。

    图生图任务与文生图一样落库 SQLite（type='img'），重启不丢、可在线查询。
    上游排队较慢（约 1~5 分钟），异步：立即返回 pending，用 GET /v1/edit/tasks/{id} 轮询。

    上游图生图硬并发=1（同会话只能 1 个编辑任务在途，实测确认），故所有编辑任务
    全局串行执行：在途任务结束后才提交下一个，避免撞上游 400 "task in progress"。
    """
    # 支持多图（images 数组）和单图（image 字段向后兼容）
    image_bytes_list: list[bytes] = []
    image_bytes: bytes | None = None
    ctype: str = "image/png"

    if req.images:
        # 多图模式：images 数组优先
        image_bytes_list = _parse_input_images(req.images)
        image_bytes = image_bytes_list[0]  # 取第一张用于 ctype 检测
    elif req.image:
        data, ctype = _parse_input_image(req.image)
        if data is None:  # 传入的是 URL，先下载字节
            data = await imagefree_client.download_image(req.image, 60.0, config.MAX_IMAGE_BYTES)
            ctype = imagefree_client.detect_mime(data)
        else:  # data URI：以魔数判定为准，修正客户端可能填错的 content_type
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

    # 多图模式：仅支持 base64 直传的提供商（aifreeforever、minimaxh3）
    # imagefree 上游只支持单图，多图时走非 imagefree 提供商路由
    if len(image_bytes_list) > 1:
        model = _normalize_model(req.model)
        if _provider_prefix(model) == "imagefree":
            # imagefree 只支持单图，降级为仅用第一张
            image_bytes = image_bytes_list[0]
            job_id = await _dispatch_edit(req.model, req.prompt, image_bytes, req.download)
            return TaskInfo(**task_to_public(db.get_public(job_id)))

    if len(image_bytes_list) <= 1:
        # 单图模式：走既有逻辑
        image_bytes = image_bytes_list[0] if image_bytes_list else image_bytes
        job_id = await _dispatch_edit(req.model, req.prompt, image_bytes, req.download)
    else:
        # 多图模式：直调 provider（非 imagefree 路由）
        job_id = await _dispatch_edit_multi(req.model, req.prompt, image_bytes_list, req.download)
    return TaskInfo(**task_to_public(db.get_public(job_id)))  # M8: 轻量投影


async def _run_edit_job(job_id: str, image: bytes, ctype: str, prompt: str,
                        download: bool, model: str = "default") -> None:
    """后台执行图生图全链路，状态/结果写入 SQLite（type='img'）。

    双层互斥保证不撞上游并发=1：
      - 进程内 asyncio 锁（快速路径）：未启用代理池用全局 _EDIT_LOCK；启用代理池按代理分锁。
      - 跨进程文件锁（多进程/多实例也可靠）：拿到 asyncio 锁后，再抢对应 key 的文件锁，
        持锁期间执行完整链路（含轮询到终态，上游并发窗口=提交到结束），完成后释放。
    """
    _EDIT_PENDING.add(job_id)
    try:
        proxy = await _EDIT_PROXY_POOL.acquire_proxy()
        key = proxy or "default"
        local_lock = _EDIT_PROXY_POOL.lock_for(key) if proxy else _EDIT_LOCK
        async with local_lock:  # 进程内串行（同 key）
            token = await _acquire_edit_mutex(key)  # 跨进程串行（同 key）
            if not token:
                db.mark_finished(job_id, "error", None,
                                 "图生图繁忙：其他实例正在生成同一出口通道，请稍后重试", None)
                return
            try:
                await _run_edit_chain(job_id, image, ctype, prompt, download, model, proxy)
            finally:
                _release_edit_mutex(key, token)
    finally:
        _EDIT_PROXY_POOL.release_proxy(proxy)
        _EDIT_PENDING.discard(job_id)


def _is_edit_slot_wedged(err: object) -> bool:
    """上游并发槽被占（孤儿任务遗留）的判定：429 "task in progress" 是瞬态，等待自愈后重试。"""
    msg = str(err).lower()
    return "already have an image editing task" in msg or "task in progress" in msg


async def _run_edit_chain(job_id: str, image: bytes, ctype: str, prompt: str,
                          download: bool, model: str = "default",
                          proxy: str | None = None) -> None:
    """真正执行图生图提交（持锁后调用）。proxy 指定则全程走该住宅代理会话。

    上游并发槽瞬态占用（孤儿任务遗留的 429 "task in progress"）→ 等待并重试有限次，
    通常几分钟内随孤儿任务完成自愈，避免任务直接失败。其余错误不重试。
    """
    t0 = time.monotonic()
    last_err: str | None = None
    for attempt in range(1, config.EDIT_RETRY_MAX + 1):
        # 从 per-key token 池取 token（key=代理 URL → 该代理预取的池；proxy=None → direct 池）。
        # token 已在池侧预取时带对应代理解好，提交直接复用，无需本任务内联求解。
        token = await engine.acquire_token(key=proxy or "direct")
        if not token:
            db.mark_finished(job_id, "error", None,
                             "人机验证 token 暂不可用（cf_solver 不可用或熔断中），请稍后重试",
                             time.monotonic() - t0)
            return
        try:
            public_url = await imagefree_client.upload_edit_image(
                config.BASE_URL, image, ctype, proxy=proxy)
            tid = await imagefree_client.submit_edit(
                config.BASE_URL, public_url, config.apply_model(prompt, model), token,
                proxy=proxy)
            db.update_upstream_task(job_id, tid)
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
                # 重试满仍是槽占用（孤儿上游任务卡住）→ 明确报错，不无限重试
                db.mark_finished(job_id, "error", None,
                                 f"图生图失败（重试 {config.EDIT_RETRY_MAX} 次仍被上游占用）: {e}",
                                 time.monotonic() - t0)
            else:
                db.mark_finished(job_id, "error", None, f"图生图失败: {e}",
                                 time.monotonic() - t0)
            return
    else:  # pragma: no cover - 循环内必然 return/break，理论不可达
        db.mark_finished(job_id, "error", None,
                         f"图生图失败（重试 {config.EDIT_RETRY_MAX} 次仍被上游占用）: {last_err}",
                         time.monotonic() - t0)
        return
    if not download:
        db.mark_finished(job_id, "completed", result["image"], None, time.monotonic() - t0)
        return
    # 需要下载结果图 base64
    try:
        raw = await imagefree_client.download_image(result["image"], 60.0, config.MAX_IMAGE_BYTES)
        mime = imagefree_client.detect_mime(raw)
        db.mark_finished(job_id, "completed", result["image"], None, time.monotonic() - t0,
                         imagefree_client.to_base64(raw, mime), mime)
    except Exception as e:
        log.warning("图生图结果下载失败（不影响 URL 交付）: %s", e)
        db.mark_finished(job_id, "completed", result["image"], None, time.monotonic() - t0)


@app.get("/v1/edit/tasks/{job_id}", response_model=TaskInfo)
async def get_edit_task(job_id: str):
    """查询图生图任务结果（持久化于 SQLite）。"""
    task = db.get_public(job_id)  # M8: 轻量投影，不读 prompt
    if not task:
        raise AppError(ErrorCodes.NOT_FOUND, "图生图任务不存在", 404)
    return TaskInfo(**task_to_public(task))


@app.get("/v1/models")
async def models():
    """全提供商模型列表。id 格式 `<提供商>/<上游真实模型名>`，capabilities 标能力。"""
    providers_bootstrap()
    groups = registry.grouped()
    return {"items": groups, "count": sum(len(v) for v in groups.values()),
            "note": "模型 id 命名：<提供商前缀>/<上游真实模型名>；capabilities 含 txt2img/img2img/txt2vid"}


@app.get("/v1/providers")
async def providers():
    """提供商看板：能力/模型数/账号需求/每请求代理需求/实时余额。"""
    providers_bootstrap()
    summary = registry.provider_summary()
    # 实时额度（尽力，不阻塞）
    for prefix, p in registry.providers.items():
        try:
            c = await p.credits()
            summary[prefix]["credits"] = c
        except Exception:
            summary[prefix]["credits"] = None
    return {"items": summary, "count": len(summary)}


@app.get("/v1/account-pool")
async def account_pool_dashboard():
    """号池看板：各提供商账号数/余额/自动注册状态/注册记录（黑匣子打开）。"""
    from .account_pool import account_pool
    from .email_pool import email_pool
    return {
        "accounts": account_pool.dashboard(),
        "email_pool": email_pool.stats(),
    }


@app.get("/v1/tasks")
async def list_tasks(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, description="筛选：pending/processing/completed/error"),
    model: str | None = Query(None, description="筛选：模型 id，如 imagefree/default"),
    sort: str = Query("created_at", description="排序字段：created_at/duration_sec"),
):
    """任务列表，按创建时间降序，支持分页和筛选。"""
    from .db import task_to_public
    items, total = db.list_tasks(
        limit=limit, offset=offset,
        status=status, model=model,
        sort=sort,
    )
    return {
        "items": [task_to_public(t) for t in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/v1/tasks/{task_id}", response_model=TaskInfo)
async def get_task(task_id: str):
    task = db.get(task_id)  # 用 get 而非 get_public，返回完整字段含 prompt
    if not task:
        raise AppError(ErrorCodes.NOT_FOUND, "task 不存在", 404)
    return TaskInfo(**task_to_public(task))


@app.get("/v1/meta")
async def meta():
    """暴露站点配置，方便调用方集成。"""
    return {"sitekey": config.SITEKEY, "aspect_ratios": config.ASPECT_RATIOS,
            "supported_resolutions": ["1K", "2K", "4K", "480p", "720p"]}


# ── 品牌静态资源（听风AI logo）──────────────────
_logo_sm = Path(__file__).parent / "static" / "tingfeng-logo-sm.png"
_logo_md = Path(__file__).parent / "static" / "tingfeng-logo-md.png"


@app.get("/static/logo.png", include_in_schema=False)
async def logo_small():
    if _logo_sm.exists():
        return FileResponse(_logo_sm, media_type="image/png",
                            headers={"Cache-Control": "public, max-age=3600"})
    raise AppError(ErrorCodes.NOT_FOUND, "Logo not found", 404)


@app.get("/static/logo-md.png", include_in_schema=False)
async def logo_medium():
    if _logo_md.exists():
        return FileResponse(_logo_md, media_type="image/png",
                            headers={"Cache-Control": "public, max-age=3600"})
    raise AppError(ErrorCodes.NOT_FOUND, "Logo not found", 404)


@app.get("/v1/stats")
async def get_stats():
    """总量统计 + 实时并发/排队 + 按日/月拆分 + 平均出图耗时。"""
    overview = await gallery_cache.get("stats:overview")
    if overview is None:
        overview = db.stats_overview()
        await gallery_cache.set("stats:overview", overview)
    daily = await gallery_cache.get("stats:daily:14")
    if daily is None:
        daily = db.stats_daily(14)
        await gallery_cache.set("stats:daily:14", daily)
    monthly = await gallery_cache.get("stats:monthly:12")
    if monthly is None:
        monthly = db.stats_monthly(12)
        await gallery_cache.set("stats:monthly:12", monthly)
    live = engine.snapshot()
    ssnap = solver_guard.snapshot()
    return {
        **overview,
        "processing": live["processing"],
        "queued": live["queued"],
        "queue_capacity": live["queue_capacity"],
        "workers": live["workers"],
        "uptime_seconds": live["uptime_seconds"],
        "uptime_human": _uptime_human(live["uptime_seconds"]),
        "daily": daily,
        "monthly": monthly,
        # ── solver 求解统计 ──
        "solver": {
            "status": ssnap["solver_status"],
            "solve_total": ssnap["solve_total"],
            "solve_success_total": ssnap["solve_success_total"],
            "solve_failure_total": ssnap["solve_failure_total"],
            "solve_avg_seconds": ssnap["solve_avg_seconds"],
            "window_success_rate": ssnap["window_success_rate"],
            "window_solve_count": ssnap["window_solve_count"],
            "window_avg_seconds": ssnap["window_avg_seconds"],
            "consecutive_failures": ssnap["consecutive_failures"],
            "circuit_open": ssnap["circuit_open"],
            "failure_reasons": ssnap["failure_reasons"],
            "rejected_total": ssnap["rejected_total"],
            "token_pools": live["token_pools"],
        },
    }


@app.get("/v1/gallery")
async def gallery(limit: int = Query(config.GALLERY_LIMIT, ge=1, le=100),
                  password: str | None = Query(None, description="画廊密码（IF_GALLERY_PASSWORD 非空时必填）")):
    """最近完成的 N 条作品（画廊）。

    IF_GALLERY_PASSWORD 配置了密码时，需传 ?password=xxx 验证通过才返回数据。
    """
    pwd = config.IF_GALLERY_PASSWORD
    if pwd:
        if not password or not hmac.compare_digest(password, pwd):
            raise AppError(ErrorCodes.UNAUTHORIZED, "画廊密码错误", 403)
    cache_key = f"gallery:{limit}"
    cached = await gallery_cache.get(cache_key)
    if cached is not None:
        return cached
    items = db.recent_images(limit)
    out = []
    for t in items:
        out.append({
            "image_url": t["image_url"],
            "image_mime": t.get("image_mime"),
            "prompt": t["prompt"],
            "aspect_ratio": t["aspect_ratio"],
            "duration_sec": t["duration_sec"],
            "finished_at": t["finished_at"],
        })
    result = {"items": out, "count": len(out)}
    await gallery_cache.set(cache_key, result)
    return result


@app.get("/v1/errors")
async def errors(limit: int = Query(20, ge=1, le=100)):
    """最近失败的请求明细（错误原因/耗时），在线排查，无需登服务器。

    MEDIUM-4: 不回传完整 prompt（可能含个人信息），仅截断前 60 字符用于定位。
    """
    items = db.recent_errors(limit)
    out = []
    for t in items:
        out.append({
            "id": t["id"],
            "status": t["status"],
            "error": t["error"],
            "prompt_preview": (t["prompt"] or "")[:60],
            "aspect_ratio": t["aspect_ratio"],
            "duration_sec": t["duration_sec"],
            "created_at": t["created_at"],
        })
    total = len(out)
    return {"items": out, "count": total, "total": total}


# ── M4: Prometheus 文本格式指标端点 ──────────────────
# 不引入 prometheus_client 依赖，输出标准 text/plain exposition（Prometheus 原生可抓）。
# 覆盖：请求/出图/失败/在途/排队/token 池水位/DB 行数/进程内存与运行时长/solver 求解质量。
@app.get("/metrics", include_in_schema=False)
async def metrics():
    snap = engine.snapshot()
    ov = db.stats_overview()
    ssnap = solver_guard.snapshot()  # solver 快照只取一次，下方复用
    success_total = ssnap["solve_success_total"]
    # 总耗时用原始累计值（solver_guard 未取整），避免 round(avg)×count 的累计误差
    duration_sum = ssnap["solve_total_duration"]
    window_rate = ssnap["window_success_rate"]
    lines = [
        "# HELP imagefree_requests_total 累计请求数",
        "# TYPE imagefree_requests_total counter",
        f"imagefree_requests_total {ov['total_requests']}",
        "# HELP imagefree_images_total 累计成功出图数",
        "# TYPE imagefree_images_total counter",
        f"imagefree_images_total {ov['total_images']}",
        "# HELP imagefree_errors_total 累计失败数",
        "# TYPE imagefree_errors_total counter",
        f"imagefree_errors_total {ov['total_errors']}",
        "# HELP imagefree_processing 当前生成中的任务数",
        "# TYPE imagefree_processing gauge",
        f"imagefree_processing {engine.processing}",
        "# HELP imagefree_queued 当前排队任务数",
        "# TYPE imagefree_queued gauge",
        f"imagefree_queued {engine.queue.qsize()}",
        "# HELP imagefree_edit_inflight 图生图在途/排队任务数",
        "# TYPE imagefree_edit_inflight gauge",
        f"imagefree_edit_inflight {len(_EDIT_PENDING)}",
        "# HELP imagefree_token_pool 当前 token 池水位",
        "# TYPE imagefree_token_pool gauge",
        f"imagefree_token_pool {engine.token_pool.qsize()}",
        "# HELP imagefree_db_rows 请求记录总量",
        "# TYPE imagefree_db_rows gauge",
        f"imagefree_db_rows {db.count()}",
        "# HELP imagefree_uptime_seconds 服务运行时长(秒)",
        "# TYPE imagefree_uptime_seconds counter",
        f"imagefree_uptime_seconds {snap['uptime_seconds']}",
        # ── solver 求解质量（M6，来自 solver_guard.snapshot()）──
        "# HELP imagefree_solve_total Turnstile 求解成功/失败累计数",
        "# TYPE imagefree_solve_total counter",
        f'imagefree_solve_total{{result="success"}} {success_total}',
        f'imagefree_solve_total{{result="failure"}} {ssnap["solve_failure_total"]}',
        "# HELP imagefree_solve_failures_by_reason 按原因分类的求解失败累计数",
        "# TYPE imagefree_solve_failures_by_reason counter",
        *[f'imagefree_solve_failures_by_reason{{reason="{r}"}} {ssnap["failure_reasons"].get(r, 0)}'
          for r in REASON_CATEGORIES if ssnap["failure_reasons"].get(r, 0)],
        "# HELP imagefree_solve_duration_seconds 求解总耗时(秒)",
        "# TYPE imagefree_solve_duration_seconds counter",
        f"imagefree_solve_duration_seconds_sum {duration_sum}",
        f"imagefree_solve_duration_seconds_count {success_total}",
        "# HELP imagefree_solve_window_success_rate 近窗口求解成功率(0-1)",
        "# TYPE imagefree_solve_window_success_rate gauge",
        f"imagefree_solve_window_success_rate {window_rate if window_rate is not None else 0}",
        "# HELP imagefree_solve_window_count 近窗口求解次数",
        "# TYPE imagefree_solve_window_count gauge",
        f"imagefree_solve_window_count {ssnap['window_solve_count']}",
        "# HELP imagefree_solve_consecutive_failures 连续求解失败次数",
        "# TYPE imagefree_solve_consecutive_failures gauge",
        f"imagefree_solve_consecutive_failures {ssnap['consecutive_failures']}",
        "# HELP imagefree_solver_circuit_open solver 熔断是否开启(1=开启)",
        "# TYPE imagefree_solver_circuit_open gauge",
        f"imagefree_solver_circuit_open {1 if ssnap['circuit_open'] else 0}",
        "# HELP imagefree_solve_rejected_total token 被上游拒绝累计数",
        "# TYPE imagefree_solve_rejected_total counter",
        f"imagefree_solve_rejected_total {ssnap['rejected_total']}",
        "# HELP imagefree_token_wait_timeout_total token 池空等待超时累计次数",
        "# TYPE imagefree_token_wait_timeout_total counter",
        f"imagefree_token_wait_timeout_total {engine.token_pool_manager.wait_timeout_total}",
        "# HELP imagefree_token_pool_watermark 各 token 池水位",
        "# TYPE imagefree_token_pool_watermark gauge",
        f'imagefree_token_pool_watermark{{pool="direct"}} {engine.token_pool.qsize()}',
    ]
    # per-proxy 池水位（跳过 direct，避免与上面的 direct 系列重复）
    pools = engine.token_pool_manager.pools_snapshot()
    pool_items = list(pools.values()) if isinstance(pools, dict) else pools
    for p in pool_items:
        key = p.get("key", "") if isinstance(p, dict) else str(p)
        if key == "direct":
            continue
        size = p.get("size", 0) if isinstance(p, dict) else 0
        label = key if key.startswith("proxy:") else f"proxy:{key}"
        lines.append(f'imagefree_token_pool_watermark{{pool="{label}"}} {size}')
    # L1(审计): 补 charset，中文 HELP 在严格客户端才能正确解码
    return PlainTextResponse("\n".join(lines) + "\n",
                             media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/v1/logs")
async def get_logs(lines: int = Query(50, ge=1, le=200)):
    """返回最近 N 行日志（内存环形缓冲区，最多 200 条）。"""
    return {"logs": log_buffer_handler.snapshot(lines)}


@app.get("/v1/dead-letter-queue")
async def dead_letter_queue(limit: int = Query(20, ge=1, le=100)):
    """死信队列：重试耗尽的失败任务列表，支持重试与清空。"""
    items = db.list_dlq(limit)
    return {"items": items, "count": len(items)}


@app.post("/v1/dead-letter-queue/{task_id}/retry")
async def retry_dlq_task(task_id: str, request: Request):
    """从死信队列移除指定任务（清空记录，重新入队重试语义）。"""
    client_ip = request.client.host if request.client else "unknown"
    audit_log.record("dlq.retry", client_ip, f"task:{task_id}", "重试死信队列任务")
    db.retry_dlq(task_id)
    return {"status": "ok", "detail": f"任务 {task_id} 已从死信队列移除"}


@app.delete("/v1/dead-letter-queue")
async def clear_dlq():
    """清空死信队列所有记录。"""
    db.clear_dlq()
    return {"status": "ok", "detail": "死信队列已清空"}


@app.get("/v1/proxy-pool")
async def get_proxy_pool():
    """代理池实时状态：住宅代理数/免费代理数/可用数/冷却数 + 前 20 条明细。"""
    from .proxy_pool import proxy_pool
    return proxy_pool.snapshot()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)
