"""管理面路由包（P0-7 拆分自原 admin.py）。

子模块各持 `router = APIRouter()`，本 `__init__.py` 创建主 `router` 并 `include_router`
合并 query / write 路由。旧 `api/routes/admin.py` 垫片 re-export 本包的 `router` 与全部
公共函数（metrics / _gallery_auth 等），保证 `from api.routes.admin import router` /
`from api.routes.admin import metrics` / `import api.routes.admin as m; m.engine` 全可用。

模块级 `engine`/`db`/`solver_guard`/`registry`/`provider_probe`/`log_buffer_handler` 等
通过 `from ._common import *` 暴露到本包命名空间，test_token_pool.py 的
`admin.engine`/`admin.db`/`admin.solver_guard` monkeypatch 不受影响。
"""

from __future__ import annotations

from . import (
    query,  # noqa: F401  (子模块 import 触发 @router 装饰器注册路由)
    write,  # noqa: F401  (子模块 import 触发 @router 装饰器注册路由)
)
from ._common import *  # noqa: F401,F403  (re-export 共享依赖 + router 单例到包命名空间)
from ._common import router  # noqa: F401  (显式绑定，消除 F405 star-import 误报)

# 主 router 单例来自 _common（query/write 子模块都用同一个 router 注册路由）。
# `from api.routes.admin import router` 拿到挂了全部路由的单一 APIRouter。
# re-export 各子模块的公共函数，保证旧 import 路径可用：
# `from api.routes.admin import metrics` / `... import _gallery_auth` 等。
from .query import (  # noqa: E402,F401
    _EMAIL_SOURCE_HOME_URLS,
    _gallery_auth,
    _gallery_signed_url,
    _gallery_verify_sig,
    account_pool_dashboard,
    audit_search,
    cost_overview,
    diagnostics,
    email_sources,
    error_aggregates,
    errors,
    frontend_errors_snapshot,
    gallery,
    gallery_sign,
    get_logs,
    get_proxy_pool,
    get_proxy_subscription,
    get_routing_records,
    get_slow_requests,
    get_stats,
    log_websocket,
    metrics,
    models,
    providers,
    report_frontend_error,
    slow_view,
    sse_stats,
)
from .write import (  # noqa: E402,F401
    clear_dlq,
    dead_letter_queue,
    retry_dlq_task,
)

__all__ = ["router"]
