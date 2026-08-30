"""IMP-19: 图生图代理池并行上限测试。

验证 _EditProxyPool 新增的 asyncio.Semaphore sem_inflight:
- acquire_proxy 改为 async，先获取信号量再 round-robin
- release_proxy 释放信号量
- 未启用代理池时信号量不限制

注意：此测试独立运行，不依赖 conftest 中的集成测试 fixture。
_EditProxyPool 在 api.dispatch_edit 中定义，导入会触发 meta 模块级
代码执行（DB 初始化、prometheus 注册等）。
"""

import asyncio
import os
import tempfile

import pytest


def _import_pool_cls():
    """设置临时环境变量后导入 _EditProxyPool。

    仅在模块级导入成功时缓存结果，避免重复导入问题。
    """
    _tmp_db = tempfile.mktemp(suffix=".db")
    os.environ["IF_DB_FILE"] = _tmp_db
    os.environ["IF_ACCOUNT_AUTO"] = "0"
    os.environ["IF_MOCK_REGISTER"] = "1"
    from api.dispatch_edit import _EditProxyPool

    return _EditProxyPool


_EditProxyPool = _import_pool_cls()


class TestEditProxyPoolInflight:
    """_EditProxyPool 信号量测试。"""

    @pytest.mark.asyncio
    async def test_acquire_proxy_is_async(self):
        """acquire_proxy 应改为 async 可等待。"""
        pool = _EditProxyPool()
        # 不启用代理池时不阻塞
        result = await pool.acquire_proxy()
        assert result is None

    @pytest.mark.asyncio
    async def test_sem_inflight_limits_concurrency(self, monkeypatch):
        """sem_inflight 应限制并发代理数。"""
        from api import config

        monkeypatch.setattr(config, "EDIT_PROXY_PARALLEL", 2)
        pool = _EditProxyPool()
        pool.proxies = ["http://proxy1:8080", "http://proxy2:8080"]
        # 设置信号量上限为 1：同一时刻只能有 1 个代理会话在途
        pool.sem_inflight = asyncio.Semaphore(1)

        # 获取第一个代理
        p1 = await pool.acquire_proxy()
        assert p1 is not None

        # 第二个 acquire 应阻塞（信号量已用完）
        task = asyncio.create_task(pool.acquire_proxy())
        await asyncio.sleep(0.15)
        assert not task.done(), "信号量应限制并发"

        # 释放第一个代理后，第二个应能获取
        pool.release_proxy(p1)
        p2 = await asyncio.wait_for(task, timeout=1.0)
        assert p2 is not None

        pool.release_proxy(p2)

    @pytest.mark.asyncio
    async def test_release_proxy_releases_semaphore(self, monkeypatch):
        """release_proxy 应释放信号量。"""
        from api import config

        monkeypatch.setattr(config, "EDIT_PROXY_PARALLEL", 2)
        pool = _EditProxyPool()
        pool.proxies = ["http://proxy1:8080"]
        pool.sem_inflight = asyncio.Semaphore(1)

        p1 = await pool.acquire_proxy()
        assert p1 is not None
        assert pool.sem_inflight.locked()

        pool.release_proxy(p1)
        assert not pool.sem_inflight.locked()

    @pytest.mark.asyncio
    async def test_pool_disabled_no_semaphore_limit(self):
        """未启用代理池时信号量不限制。"""
        pool = _EditProxyPool()
        # 池未启用（空 proxies 或 EDIT_PROXY_PARALLEL <= 1）
        result = await pool.acquire_proxy()
        assert result is None
        # release_proxy 不会崩溃
        pool.release_proxy(None)
        pool.release_proxy("http://some-proxy")

    @pytest.mark.asyncio
    async def test_release_proxy_with_none(self):
        """release_proxy(None) 不应崩溃。"""
        pool = _EditProxyPool()
        pool.release_proxy(None)  # 不应抛异常

    @pytest.mark.asyncio
    async def test_round_robin_with_semaphore(self, monkeypatch):
        """信号量下 round-robin 分配仍正确。"""
        from api import config

        monkeypatch.setattr(config, "EDIT_PROXY_PARALLEL", 3)
        pool = _EditProxyPool()
        pool.proxies = ["http://p1", "http://p2", "http://p3"]
        pool.sem_inflight = asyncio.Semaphore(3)

        proxies = set()
        for _ in range(3):
            p = await pool.acquire_proxy()
            assert p is not None
            proxies.add(p)
        assert len(proxies) == 3, "round-robin 应遍历所有代理"

        for p in proxies:
            pool.release_proxy(p)
