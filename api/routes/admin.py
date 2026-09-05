"""管理面端点垫片（P0-7 拆分后兼容层）。

原 admin.py（780 行）已拆分为 `api/routes/admin/` 包：
- `admin/__init__.py`：主 `router` 单例（来自 _common，query/write 共享注册）
- `admin/_common.py`：共享 import + `router = APIRouter()` 单例
- `admin/query.py`：查询类只读端点（models/providers/cost/stats/gallery/logs/...）
- `admin/write.py`：写操作端点（DLQ 重试/清空，带 check_admin_key 鉴权）

本文件保留全部旧 import 路径兼容：`from api.routes.admin import router` /
`from api.routes.admin import metrics` / `import api.routes.admin as m; m.engine`。
不要直接编辑本文件——改动请到 `admin/` 子包对应文件。
"""

from __future__ import annotations

# 模块级对象 re-export（test_token_pool.py 通过 admin.engine/admin.db/admin.solver_guard monkeypatch）
from ._common import (  # noqa: F401
    _SLOW_PAGE,
    _slow_log,
    _uptime_human,
    audit_log,
    check_admin_key,
    config,
    db,
    engine,
    gallery_cache,
    log,
    log_buffer_handler,
    metrics_v2,
    provider_probe,
    register_ws,
    registry,
    solver_guard,
    unregister_ws,
)

# 主 router 单例（挂全部路由）
# 公共函数 re-export（保持旧 import 路径可用）
from .admin import (  # noqa: F401
    _EMAIL_SOURCE_HOME_URLS,
    _gallery_auth,
    _gallery_signed_url,
    _gallery_verify_sig,
    account_pool_dashboard,
    audit_search,
    clear_dlq,
    cost_overview,
    dead_letter_queue,
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
    retry_dlq_task,
    router,  # noqa: F401
    slow_view,
    sse_stats,
)
