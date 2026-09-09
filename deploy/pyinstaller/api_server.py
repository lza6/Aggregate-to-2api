# -*- coding: utf-8 -*-
"""PyInstaller 后端入口（sidecar uvicorn.exe）。全栈：主 API + 内嵌 cf_solver。"""

import os
import sys

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    sys.path.insert(0, sys._MEIPASS)
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.main import app  # noqa: E402


def _embed_solver() -> None:
    """把 Turnstile 求解器内嵌进主 API：注册 /cf/turnstile + /cf/result 路由转发 solver 实例。
    用 routes.insert(0) 确保排在 landing '/' mount（catch-all）之前，避免被截获 404。
    """
    if not getattr(sys, "frozen", False):
        return
    if os.environ.get("IF_DESKTOP_NO_SOLVER", "0") == "1":
        return
    try:
        import importlib.util
        import logging

        base = getattr(sys, "_MEIPASS", os.getcwd())
        solver_api = os.path.join(base, "deploy", "cf_solver", "api_server.py")
        if not os.path.exists(solver_api):
            return
        spec = importlib.util.spec_from_file_location("deploy.cf_solver.api_server", solver_api)
        solver_mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = solver_mod
        spec.loader.exec_module(solver_mod)

        server = solver_mod.ClearanceAPIServer(
            headless=True, thread=2, page_count=1,
            proxy_support=False, proxy_file="proxies.txt", cleanup_interval_minutes=10,
        )

        import fastapi

        async def _turnstile(url: str = fastapi.Query(...), sitekey: str = fastapi.Query(...)):
            return await server.process_turnstile(url=url, sitekey=sitekey)

        async def _result(task_id: str = fastapi.Query(..., alias="id")):
            return await server.get_result(task_id=task_id)

        r1 = fastapi.routing.APIRoute("/cf/turnstile", _turnstile, methods=["GET"], include_in_schema=False)
        r2 = fastapi.routing.APIRoute("/cf/result", _result, methods=["GET"], include_in_schema=False)
        # 插到路由表最前（在 landing '/' mount catch-all 之前）
        app.router.routes.insert(0, r2)
        app.router.routes.insert(0, r1)

        os.environ["IF_CF_SOLVER_URL"] = "http://127.0.0.1:8100/cf"
        import tempfile
        open(os.path.join(tempfile.gettempdir(), "solver_embed_ok"), "w").write("ok")
        logging.getLogger("imagefree_api").info("[desktop] cf_solver 已内嵌 /cf/turnstile + /cf/result")
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("imagefree_api").warning("[desktop] cf_solver 内嵌失败: %s", exc)


if __name__ == "__main__":
    import uvicorn

    _embed_solver()
    host = os.environ.get("IF_HOST", "127.0.0.1")
    port = int(os.environ.get("IF_PORT", "8100"))
    uvicorn.run(app, host=host, port=port, log_level="info")
