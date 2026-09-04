"""imagefree_api 主服务：应用组装入口（v4.2 拆分后 <300 行）。

挂载路由（api.routes）、中间件、全局异常处理器、前端管理面板、生命周期。
业务逻辑已迁移至：routes/、dispatch.py、dispatch_edit.py、lifespan.py、
handlers.py、bg_tasks.py、models.py、meta.py、sse_events.py。
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .context import RequestContextMiddleware
from .meta import db, engine, gallery_cache  # noqa: F401  (test conftest 依赖 api.main.engine)
from .lifespan import lifespan
from .handlers import register_exception_handlers
from .routes import api_router

log = logging.getLogger("imagefree_api")

# ── 顶层挂载日志缓冲区（在 uvicorn 模块导入阶段直接生效）──
from .log_buffer import log_buffer  # noqa: E402

_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
if log_buffer not in _root_logger.handlers:
    _root_logger.addHandler(log_buffer)

# P3-6: 禁止 uvicorn.access 原生日志冒泡到 root（其 AccessFormatter 会输出完整
# URL 含 query string，?api_key=xxx 传入时完整 Key 泄露进 log_buffer）。
# 访问日志由 context.py 中间件自定义写入（只记 path 不含 query），uvicorn.access
# 原生日志对本服务无增量信息，禁用冒泡即彻底断绝 query 泄露通道。
logging.getLogger("uvicorn.access").propagate = False
# 同理：httpx 客户端日志也会记录完整请求 URL（含 query 的 api_key）。本服务的
# 出站请求 URL 不含敏感 Key，但入站 TestClient/httpx 日志统一收敛，防 query 泄露。
# httpx 访问日志无运维增量（上游调用日志由 providers 层自行记录），禁用冒泡。
logging.getLogger("httpx").propagate = False

# ── P3-3: 生产安全响应头中间件 ──────────────────────────
# 仅当 config.IF_SECURITY_HEADERS_ENABLED 为 True 时注入；关闭=不注入任何安全头（最小回滚）。
# CSP 独立开关 config.IF_CSP_ENABLED（默认关闭），经许可后才注入宽松 CSP，避免误杀面板/画廊。
class SecurityHeadersMiddleware:
    """纯 ASGI 中间件：向每个 HTTP 响应注入生产安全响应头。

    注入头（IF_SECURITY_HEADERS_ENABLED=True 时）：
      - Strict-Transport-Security: max-age=31536000; includeSubDomains（仅 HTTPS 请求）
      - X-Content-Type-Options: nosniff
      - X-Frame-Options: DENY
      - Referrer-Policy: strict-origin-when-cross-origin
    当 IF_CSP_ENABLED=True 时额外注入宽松 CSP：
      default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline';
      script-src 'self' 'unsafe-inline'; connect-src 'self'
    说明：X-Frame-Options: DENY 仅禁止他人页面对本服务的 iframe 嵌入，不破坏本服务自身的
    管理面板/落地页渲染；JSON API 响应不含 inline HTML/脚本，不受 header 注入影响。
    """

    # 常量头（只在需要时按请求注入，避免无条件设置导致 head/错误响应膨胀）
    _HSTS = b"max-age=31536000; includeSubDomains"
    _XCTO = b"nosniff"
    _XFO = b"DENY"
    _RRP = b"strict-origin-when-cross-origin"
    _CSP = (
        b"default-src 'self'; "
        b"img-src 'self' data: https:; "
        b"style-src 'self' 'unsafe-inline'; "
        b"script-src 'self' 'unsafe-inline'; "
        b"connect-src 'self'"
    )

    def __init__(self, app):
        self.app = app
        self._enabled = bool(getattr(config, "IF_SECURITY_HEADERS_ENABLED", False))
        self._csp_enabled = bool(getattr(config, "IF_CSP_ENABLED", False))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self._enabled:
            await self.app(scope, receive, send)
            return

        is_https = scope.get("scheme") == "https"

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {k.lower() for k, _ in headers}
                if b"x-content-type-options" not in existing:
                    headers.append((b"X-Content-Type-Options", self._XCTO))
                if b"x-frame-options" not in existing:
                    headers.append((b"X-Frame-Options", self._XFO))
                if b"referrer-policy" not in existing:
                    headers.append((b"Referrer-Policy", self._RRP))
                if is_https and b"strict-transport-security" not in existing:
                    headers.append((b"Strict-Transport-Security", self._HSTS))
                if self._csp_enabled and b"content-security-policy" not in existing:
                    headers.append((b"Content-Security-Policy", self._CSP))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


# ── App 组装 ──
app = FastAPI(
    title="imagefree API",
    version="7.7.4",
    description="AI 图像生成开放接口：自动完成 Cloudflare Turnstile 人机验证，无感调用。"
    "高并发异步队列，文档见管理台 /admin，Swagger 见 /docs。",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in (config.CORS_ORIGINS or "*").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── P3-3: 生产安全响应头注入（默认开启；关闭=最小回滚）──
# 注入 X-Content-Type-Options / X-Frame-Options / Referrer-Policy / Strict-Transport-Security(仅HTTPS)。
# 默认 true 不破坏现状：本 API 为 JSON 接口+管理面板，JSON 响应无 inline HTML，这些头对现有
# JS 前端无破坏（X-Frame-Options:DENY 仅影响他页 iframe 嵌本服务，管理面板自身不受影响）。
# CSP 默认关闭（config.IF_CSP_ENABLED），避免误杀面板 inline script / 画廊 CDN 图片。
app.add_middleware(SecurityHeadersMiddleware)

# ── 全局异常处理器 ──
register_exception_handlers(app)

# ── A-05: contextvars 请求上下文中间件 ──
app.add_middleware(RequestContextMiddleware)

# ── P0-安全：请求体总量上限（防恶意大 base64 正文在 4MB/张校验前耗尽内存）──
# starlette 1.6 起名为 RequestBodyLimitMiddleware；旧版本为 BodySizeLimitMiddleware。
try:
    from starlette.middleware.body_limit import RequestBodyLimitMiddleware as _BodyLimit
except ImportError:
    from starlette.middleware.body_limit import BodySizeLimitMiddleware as _BodyLimit  # type: ignore
app.add_middleware(_BodyLimit, max_body_size=config.IF_MAX_REQUEST_BODY)

# ── 挂载全部 API 路由 ──
app.include_router(api_router)

# ── 挂载前端管理面板 ──
_FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if _FRONTEND_DIR.exists():
    try:
        from fastapi.staticfiles import StaticFiles

        class SPAStaticFiles(StaticFiles):
            """SPA 深链回退：/admin/tasks 等前端路由刷新时回退 index.html（BrowserRouter 接管）。

            兼容两代 starlette 行为：
            - 旧版 get_response 返回 status_code=404 的 Response 对象 → 走 response.status_code 分支；
            - 新版（starlette ≥ 0.36 风格，生产 1.6.0 实测）直接 raise HTTPException(404)
              → 捕获异常后回退 index.html。
            assets/ 静态资源 404 保持 404（资源缺失应显式报错，不能回退成 HTML）。
            """

            async def get_response(self, path: str, scope):
                from starlette.exceptions import HTTPException as StarletteHTTPException

                try:
                    return await super().get_response(path, scope)
                except StarletteHTTPException as exc:
                    if exc.status_code == 404 and not path.startswith("assets/"):
                        return await super().get_response("index.html", scope)
                    raise

        app.mount("/admin", SPAStaticFiles(directory=str(_FRONTEND_DIR), html=True), name="admin")

        # /admin 不带斜杠时 starlette 的 StaticFiles(html=True) 会 404（它期望目录索引），
        # 用 redirect 把 /admin → /admin/ 触发 SPA 的 index.html 兜底。
        from fastapi.responses import RedirectResponse

        @app.get("/admin", include_in_schema=False)
        async def _admin_redirect() -> RedirectResponse:
            return RedirectResponse(url="/admin/", status_code=307)

        log.info("前端管理面板已挂载到 /admin（含 SPA 深链回退 + /admin→/admin/ 重定向）")
    except Exception as e:
        log.warning("前端管理面板挂载失败: %s", e)

# ── 挂载 Vue3 公开落地页（替换原单文件 docs.html 首页）──
# base '/'，须在 api_router 之后挂载：/v1/*、/docs、/metrics、/static/* 等路由已先注册，优先匹配。
# 仅未命中任何 API 路由的路径（/、/assets/*、深链）落到此处。
_LANDING_DIR = Path(__file__).parent.parent / "landing" / "dist"
if _LANDING_DIR.exists():
    try:
        from fastapi.staticfiles import StaticFiles as _SF

        app.mount("/", _SF(directory=str(_LANDING_DIR), html=True), name="landing")
        log.info("Vue3 公开落地页已挂载到 /")
    except Exception as e:
        log.warning("Vue3 公开落地页挂载失败: %s", e)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)
