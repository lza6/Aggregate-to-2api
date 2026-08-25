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
from .meta import db, engine, gallery_cache
from .lifespan import lifespan
from .handlers import register_exception_handlers
from .routes import api_router

log = logging.getLogger("imagefree_api")

# ── 顶层挂载日志缓冲区（在 uvicorn 模块导入阶段直接生效）──
from .log_buffer import log_buffer
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
if log_buffer not in _root_logger.handlers:
    _root_logger.addHandler(log_buffer)

# ── App 组装 ──
app = FastAPI(
    title="imagefree API",
    version="4.2.0",
    description="AI 图像生成开放接口：自动完成 Cloudflare Turnstile 人机验证，无感调用。"
                "高并发异步队列，文档见首页 GET /，Swagger 见 /docs。",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in (config.CORS_ORIGINS or "*").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 全局异常处理器 ──
register_exception_handlers(app)

# ── A-05: contextvars 请求上下文中间件 ──
app.add_middleware(RequestContextMiddleware)

# ── 挂载全部 API 路由 ──
app.include_router(api_router)

# ── 挂载前端管理面板 ──
_FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if _FRONTEND_DIR.exists():
    try:
        from fastapi.staticfiles import StaticFiles

        class SPAStaticFiles(StaticFiles):
            """SPA 深链回退：/admin/tasks 刷新时回退 index.html（BrowserRouter 路由接管）。"""

            async def get_response(self, path: str, scope):
                response = await super().get_response(path, scope)
                if response.status_code == 404:
                    if not path.startswith("assets/"):
                        response = await super().get_response("index.html", scope)
                return response

        app.mount("/admin", SPAStaticFiles(directory=str(_FRONTEND_DIR), html=True), name="admin")
        log.info("前端管理面板已挂载到 /admin（含 SPA 深链回退）")
    except Exception as e:
        log.warning("前端管理面板挂载失败: %s", e)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)