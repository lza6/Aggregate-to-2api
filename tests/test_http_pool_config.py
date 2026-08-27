"""IMP-27: HTTP 连接池参数化 + 上游并发控制测试。

覆盖场景：
- config 默认值正确
- _get_client() 连接池上限受配置控制
- 信号量默认值正确
- 信号量 acquire/release 工作
- 信号量上限生效（并发超过上限时阻塞）
"""
import asyncio
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class TestHttpPoolConfig:
    """连接池配置项默认值。"""

    def test_defaults_are_correct(self):
        """IF_HTTP_MAX_CONNECTIONS 默认 100，IF_HTTP_KEEPALIVE 默认 20，
        IF_UPSTREAM_MAX_INFLIGHT 由 system_spec 按本机规格自适应。"""
        import api.config as cfg
        from api.system_spec import ADAPTIVE_UPSTREAM_INFLIGHT

        assert cfg.IF_HTTP_MAX_CONNECTIONS == 100, "默认 max_connections 应为 100"
        assert cfg.IF_HTTP_KEEPALIVE == 20, "默认 max_keepalive 应为 20"

        # 上游并发上限是自适应值（默认 30 → 按规格自适应），必须与 system_spec 一致
        # 而非硬编码 30。四档规格取值为：12 / 24 / 64(向下取 2*核心) 。
        assert cfg.IF_UPSTREAM_MAX_INFLIGHT == ADAPTIVE_UPSTREAM_INFLIGHT, (
            f"默认 upstream_max_inflight 应与自适应规格一致，"
            f"实际 {cfg.IF_UPSTREAM_MAX_INFLIGHT} != 自适应 {ADAPTIVE_UPSTREAM_INFLIGHT}"
        )

    def test_env_overrides(self, monkeypatch):
        """环境变量能覆盖默认值。"""
        monkeypatch.setenv("IF_HTTP_MAX_CONNECTIONS", "50")
        monkeypatch.setenv("IF_HTTP_KEEPALIVE", "10")
        monkeypatch.setenv("IF_UPSTREAM_MAX_INFLIGHT", "5")

        # 重新加载 config 模块以让 os.getenv 重新执行
        import importlib
        import api.config as cfg
        importlib.reload(cfg)

        assert cfg.IF_HTTP_MAX_CONNECTIONS == 50
        assert cfg.IF_HTTP_KEEPALIVE == 10
        assert cfg.IF_UPSTREAM_MAX_INFLIGHT == 5


class TestTurnstileClientPoolConfig:
    """turnstile_client._get_client() 使用配置项。"""

    @staticmethod
    def _get_pool(client):
        """从 httpx.AsyncClient 中提取连接池限制。"""
        for _, transport in client._mounts.items():
            if transport is not None:
                return transport._pool
        return None

    @pytest.mark.asyncio
    async def test_pool_limits_use_config(self, monkeypatch):
        """_get_client 创建的 httpx.Limits 使用 config.IF_HTTP_MAX_CONNECTIONS
        和 config.IF_HTTP_KEEPALIVE。"""
        import api.turnstile_client as tc
        import api.config as cfg

        monkeypatch.setattr(cfg, "IF_HTTP_MAX_CONNECTIONS", 42)
        monkeypatch.setattr(cfg, "IF_HTTP_KEEPALIVE", 7)

        # 重置共享 client 以重新创建
        tc._client = None
        client = tc._get_client()
        pool = self._get_pool(client)
        assert pool is not None
        assert pool._max_connections == 42
        assert pool._max_keepalive_connections == 7

        await tc.close_client()


class TestImagefreeClientPoolConfig:
    """imagefree_client._get_client() 使用配置项。"""

    @staticmethod
    def _get_pool(client):
        """从 httpx.AsyncClient 中提取连接池限制。"""
        for _, transport in client._mounts.items():
            if transport is not None:
                return transport._pool
        return None

    @pytest.mark.asyncio
    async def test_pool_limits_use_config(self, monkeypatch):
        """_get_client 创建的 httpx.Limits 使用 config 中的连接池配置。"""
        import api.imagefree_client as ic
        import api.config as cfg

        monkeypatch.setattr(cfg, "IF_HTTP_MAX_CONNECTIONS", 77)
        monkeypatch.setattr(cfg, "IF_HTTP_KEEPALIVE", 13)

        ic._client = None
        client = ic._get_client()
        pool = self._get_pool(client)
        assert pool is not None
        assert pool._max_connections == 77
        assert pool._max_keepalive_connections == 13

        await ic.close_client()


class TestSemaphoreManager:
    """信号量管理器。"""

    def test_default_semaphore_value(self, monkeypatch):
        """信号量初始值取自 IF_UPSTREAM_MAX_INFLIGHT。"""
        import api.config as cfg
        import importlib
        import api.semaphore_manager as sm

        monkeypatch.setattr(cfg, "IF_UPSTREAM_MAX_INFLIGHT", 15)
        importlib.reload(sm)
        assert sm.upstream_semaphore._value == 15

    @pytest.mark.asyncio
    async def test_acquire_and_release(self):
        """acquire 后 value -1，release 后 value +1。"""
        from api.semaphore_manager import upstream_semaphore

        initial = upstream_semaphore._value
        await upstream_semaphore.acquire()
        assert upstream_semaphore._value == initial - 1
        upstream_semaphore.release()
        assert upstream_semaphore._value == initial

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self, monkeypatch):
        """信号量上限生效：并发超过上限的协程会阻塞。"""
        import api.config as cfg
        import api.semaphore_manager as sm

        # 临时设小信号量
        monkeypatch.setattr(cfg, "IF_UPSTREAM_MAX_INFLIGHT", 2)
        import importlib
        importlib.reload(sm)
        from api.semaphore_manager import upstream_semaphore

        # 占满 2 个槽
        await upstream_semaphore.acquire()
        await upstream_semaphore.acquire()
        assert upstream_semaphore._value == 0

        # 第 3 个 acquire 应阻塞；用超时确认
        t0 = asyncio.get_event_loop().time()
        try:
            await asyncio.wait_for(upstream_semaphore.acquire(), timeout=0.1)
            assert False, "预期超时但 acquire 立即返回"
        except asyncio.TimeoutError:
            pass

        elapsed = asyncio.get_event_loop().time() - t0
        assert elapsed >= 0.08, f"acquire 应阻塞至少 0.1s，实际 {elapsed:.3f}s"

        # 释放一个槽 → 第 3 个 acquire 应成功
        upstream_semaphore.release()
        await asyncio.wait_for(upstream_semaphore.acquire(), timeout=0.5)

        # 清理
        upstream_semaphore.release()
        upstream_semaphore.release()