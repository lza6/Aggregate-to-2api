"""pytest 共享 fixtures：环境隔离 + 临时 DB，避免测试污染真实 data/。

用法：`import pytest; from conftest import make_db` 或直接用 `db` fixture。
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# 确保项目根目录可导入 api 包（pytest 从根目录跑时自动；此处兜底）
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture
def tmp_db():
    """独立的临时 SQLite DB 实例（每用例独立，WAL 关掉避免跨用例锁文件残留）。"""
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
    """测试期间清空代理环境变量，避免本机 Clash 影响。"""
    saved = {k: os.environ.pop(k, None) for k in ("HTTP_PROXY", "HTTPS_PROXY", "IF_PROXY")}
    yield
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
