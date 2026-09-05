"""P0-7 兼容性测试：admin.py 拆分为 admin/ 包后，旧 import 路径必须全可用。

覆盖：
- `from api.routes.admin import router`（单例，挂全部路由）
- `from api.routes.admin import metrics`（函数可调用）
- `from api.routes.admin import _gallery_auth, _gallery_signed_url, _gallery_verify_sig`
- `from api.routes import admin; admin.engine / admin.db / admin.solver_guard`（模块属性，test_token_pool 依赖）
- 关键路由路径注册到 router
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.routing import APIRoute, APIWebSocketRoute


def test_router_singleton_available():
    """`from api.routes.admin import router` 必须可用且为 APIRouter。"""
    from api.routes.admin import router

    assert isinstance(router, APIRouter)
    assert len(router.routes) > 0


def test_metrics_callable_imported():
    """`from api.routes.admin import metrics` 必须可 import 且可调用。"""
    from api.routes.admin import metrics

    assert callable(metrics)


def test_gallery_helpers_importable():
    """`from api.routes.admin import _gallery_auth, _gallery_signed_url, _gallery_verify_sig`。

    test_gallery_signing.py 直接 import 这三个私有辅助，拆分后必须保留。
    """
    from api.routes.admin import _gallery_auth, _gallery_signed_url, _gallery_verify_sig

    assert callable(_gallery_auth)
    assert callable(_gallery_signed_url)
    assert callable(_gallery_verify_sig)


def test_module_level_attributes_for_monkeypatch():
    """`from api.routes import admin; admin.engine / admin.db / admin.solver_guard`。

    test_token_pool.py 通过模块属性访问 + monkeypatch，拆分后这些属性必须仍挂在
    `api.routes.admin` 命名空间下（由 __init__.py re-export）。
    """
    from api.routes import admin

    assert hasattr(admin, "engine"), "admin.engine 缺失（test_token_pool monkeypatch 依赖）"
    assert hasattr(admin, "db"), "admin.db 缺失"
    assert hasattr(admin, "solver_guard"), "admin.solver_guard 缺失"
    assert hasattr(admin, "metrics"), "admin.metrics 缺失"


def test_key_routes_registered():
    """关键路由路径必须注册到 router（拆分前后等价）。"""
    from api.routes.admin import router

    paths = set()
    for r in router.routes:
        if hasattr(r, "path"):
            paths.add(r.path)
    # 抽样断言（覆盖各子模块：只读查询/写操作鉴权/WS/gallery 签名）
    expected = {
        "/v1/models",
        "/v1/providers",
        "/v1/cost",
        "/v1/account-pool",
        "/v1/stats",
        "/v1/gallery",
        "/v1/gallery/sign",
        "/v1/errors",
        "/v1/logs",
        "/v1/logs/ws",
        "/v1/dead-letter-queue",
        "/v1/dead-letter-queue/{task_id}/retry",
        "/v1/proxy-pool",
        "/v1/email-sources",
        "/v1/routing/records",
        "/v1/slow",
        "/v1/audit",
        "/v1/diagnostics",
        "/v1/sse/stats",
        "/metrics",
    }
    missing = expected - paths
    assert not missing, f"拆分后 router 丢失路由: {missing}"


def test_legacy_module_path_admin_router():
    """旧路径 `import api.routes.admin as m; m.router` 必须仍是同一个 router 单例。"""
    import api.routes.admin as legacy
    from api.routes.admin import router

    assert legacy.router is router


def test_router_routes_are_api_or_ws_routes():
    """router.routes 元素类型契约（防 include_router 丢失类型信息）。"""
    from api.routes.admin import router

    for r in router.routes:
        assert isinstance(r, (APIRoute, APIWebSocketRoute)), f"路由类型异常: {type(r)}"
