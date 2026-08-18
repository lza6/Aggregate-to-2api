"""pytest 共享 fixtures：环境隔离 + 临时 DB + 集成测试支持。"""
import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
import pytest_asyncio

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture
def tmp_db():
    """独立的临时 SQLite DB 实例（每用例独立）。"""
    from api.db import DB

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DB(path)
    yield db
    try:
        os.unlink(path)
        for suffix in ("-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.unlink(path + suffix)
    except OSError:
        pass


@pytest.fixture
def no_proxy_env():
    """测试期间清空代理环境变量。"""
    saved = {k: os.environ.pop(k, None) for k in ("HTTP_PROXY", "HTTPS_PROXY", "IF_PROXY")}
    yield
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v


@pytest.fixture
def mock_env():
    """设置 mock 环境变量。"""
    env_vars = {
        "IF_ACCOUNT_AUTO": "0",
        "IF_MOCK_REGISTER": "1",
        "IF_MOCK_UPSTREAM": "1",
        "IF_TURNSTILE_POLL_INTERVAL": "0.2",
        "IF_TOKEN_POOL_SIZE": "2",
        "IF_DB_FILE": "data/test.db",
        "IF_PROXY": "",
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
    }
    saved = {}
    for k, v in env_vars.items():
        saved[k] = os.environ.get(k)
        os.environ[k] = v
    yield
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def wait_port(port: int, timeout: float, desc: str) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_open(port):
            return True
        time.sleep(0.3)
    return False


@pytest.fixture(scope="session")
def mock_cfsolver():
    """会话级 mock cf_solver 进程。"""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    p = subprocess.Popen(
        [sys.executable, str(_ROOT / "scripts" / "mock_cfsolver.py"), "--port", "8001"],
        cwd=str(_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=env,
    )
    if not wait_port(8001, 15, "mock solver"):
        p.kill()
        raise RuntimeError("mock cf_solver 启动超时")
    yield "http://127.0.0.1:8001"
    p.terminate()
    try:
        p.wait(timeout=5)
    except Exception:
        p.kill()


@pytest_asyncio.fixture
async def app_with_mocks(mock_cfsolver, tmp_db, no_proxy_env):
    """全 mock 集成测试环境：FastAPI 完整应用 + mock DB + mock cf_solver。

    先设置环境变量，清除已有 api 模块缓存，再导入 api.main 获得全新 app 实例。
    之后注入临时 DB 并使用 ASGITransport + lifespan 启动引擎。
    """
    # ── 设置集成测试所需环境变量 ──
    os.environ["IF_CF_SOLVER_URL"] = mock_cfsolver
    os.environ["IF_TURNSTILE_POLL_INTERVAL"] = "0.2"
    os.environ["IF_TOKEN_POOL_SIZE"] = "2"
    os.environ["IF_SYNC_TIMEOUT"] = "60"
    os.environ["IF_GENERATE_TIMEOUT"] = "120"
    os.environ["IF_MOCK_UPSTREAM"] = "1"
    os.environ["IF_MOCK_REGISTER"] = "1"
    os.environ["IF_ACCOUNT_AUTO"] = "0"
    os.environ["IF_DLQ_ENABLED"] = "1"
    os.environ["IF_IDEMPOTENCY_ENABLED"] = "1"
    os.environ["IF_PERSISTENT_QUEUE_ENABLED"] = "0"
    os.environ["IF_SOLVE_CIRCUIT_PROBE_SECONDS"] = "1"
    os.environ["IF_SOLVE_CIRCUIT_THRESHOLD"] = "3"
    # 避免 StaticFiles 挂载报错
    os.environ["IF_GALLERY_PASSWORD"] = ""
    # 避免 base64_store 写 data/ 目录
    os.environ["IF_BASE64_DIR"] = str(tempfile.mkdtemp())

    # ── 清除已有 api 模块缓存，确保全新导入 ──
    for mod_key in list(sys.modules.keys()):
        if mod_key.startswith("api"):
            del sys.modules[mod_key]

    # ── 全新导入 api.main（触发模块级代码：app 创建、路由注册等）──
    import importlib
    import api.config
    importlib.reload(api.config)
    import api.main  # noqa: F811
    importlib.reload(api.main)

    # ── 注入临时 DB ──
    api.main.db = tmp_db
    api.main.engine.db = tmp_db

    app = api.main.app

    # ── 创建 TestClient（lifespan="on" 自动启动引擎）──
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # ── 等待服务就绪 ──
        for _ in range(30):
            try:
                r = await client.get("/v1/healthz")
                if r.json().get("status") in ("ok", "degraded"):
                    break
            except Exception:
                pass
            await asyncio.sleep(0.2)
        yield client