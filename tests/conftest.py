"""pytest 共享 fixtures：环境隔离 + 临时 DB + 集成测试支持。

loop 约定（pytest-asyncio 1.4+）：不再自定义 event_loop fixture——它已被弃用且会在
asyncio_default_test_loop_scope/ fixture_loop_scope 之外另起 session loop，
导致 app 内部 worker/DB 与测试函数跨 loop 死锁（txt2img 集成测试卡 pending 的历史根因）。
统一交由 pytest-asyncio 的 session scope 管理，测试与 session fixture 共享同一 loop。
"""
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


@pytest_asyncio.fixture
async def tmp_db():
    """独立的临时 SQLite DB 实例（每用例独立）。"""
    from api.db import DB

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DB(path)
    await db._ensure_initialized()
    yield db
    try:
        await db.close()
    except Exception:
        pass
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


@pytest_asyncio.fixture(scope="session")
async def _app_instance(mock_cfsolver):
    """会话级：创建 FastAPI 应用实例（仅导入一次，避免 prometheus 注册冲突）。

    设置环境变量 -> 导入 api.main -> 手动触发 lifespan startup。
    会话级 fixture 确保整个测试会话只创建一次，所有测试用例共享。
    不依赖自定义 event_loop——统一走 pytest-asyncio 的 session loop。
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
    os.environ["IF_GALLERY_PASSWORD"] = ""
    os.environ["IF_BASE64_DIR"] = str(tempfile.mkdtemp())

    # 临时 DB 文件（会话级，共享 DB 实例）
    _db_path = tempfile.mktemp(suffix=".db")
    os.environ["IF_DB_FILE"] = _db_path

    # ── 清除已有 api 模块缓存，确保全新导入 ──
    for mod_key in list(sys.modules.keys()):
        if mod_key.startswith("api"):
            del sys.modules[mod_key]

    import api.config  # noqa: F401
    import api.main  # 首次导入，触发模块级代码执行

    # ── 手动触发 lifespan startup（引擎启动、worker 创建等）──
    _lifespan_ctx = api.main.lifespan(api.main.app)
    await _lifespan_ctx.__aenter__()

    yield api.main

    # ── 会话结束：执行 lifespan shutdown ──
    await _lifespan_ctx.__aexit__(None, None, None)

    # ── 清理临时 DB ──
    try:
        os.unlink(_db_path)
        for suffix in ("-wal", "-shm"):
            if os.path.exists(_db_path + suffix):
                os.unlink(_db_path + suffix)
    except OSError:
        pass


@pytest_asyncio.fixture(scope="session")
async def app_with_mocks(_app_instance):
    """会话级：集成测试 httpx.AsyncClient。

    共享 _app_instance 创建的应用实例，返回 httpx.AsyncClient。
    整个测试会话只创建一个 client，所有测试用例共享。
    """
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=_app_instance.app), base_url="http://test") as client:
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