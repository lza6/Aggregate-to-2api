"""P1-1（v8.0）：storage/ Redis 适配器接线测试。

验收：
- IF_STORAGE_BACKEND 未设/非 redis → request_guard.get_storage_adapter() 返回 None（单机内存模式零回归）。
- set_storage_adapter(adapter) 注入后 get_storage_adapter() 返回同一对象（lifespan startup 装配路径）。
- set_storage_adapter(None) 清空后回退 None（shutdown / 测试 teardown）。
- check_rate_limit 决策路径在单机模式下不被 storage_adapter 污染（同步入口不 await async adapter）。
"""

from __future__ import annotations

from api import request_guard


def test_default_storage_adapter_is_none(monkeypatch):
    """单机缺省：未装配 adapter → get_storage_adapter() 返回 None（零回归）。"""
    monkeypatch.setattr(request_guard, "_storage_adapter", None)
    assert request_guard.get_storage_adapter() is None


def test_set_and_clear_storage_adapter(monkeypatch):
    """set_storage_adapter 注入/清空生命周期（lifespan startup→shutdown 路径）。"""

    class _FakeAdapter:
        shutdown_called = False

        async def shutdown(self) -> None:
            self.shutdown_called = True

    fake = _FakeAdapter()
    request_guard.set_storage_adapter(fake)
    assert request_guard.get_storage_adapter() is fake
    # 清空（shutdown 后回退单机）
    request_guard.set_storage_adapter(None)
    assert request_guard.get_storage_adapter() is None


def test_check_rate_limit_unaffected_by_storage_adapter(monkeypatch):
    """单机模式：storage_adapter=None 时 check_rate_limit 走原内存分片桶路径（不污染决策）。"""

    class _FakeRequest:
        headers = {"x-forwarded-for": ""}

        @property
        def client(self):
            class _C:
                host = "127.0.0.1"

            return _C()

    monkeypatch.setattr(request_guard, "_storage_adapter", None)
    monkeypatch.setattr(request_guard, "_whitelist_ips", lambda: set())
    monkeypatch.setattr(request_guard, "_get_cached_ip_rule", lambda ip: None)
    monkeypatch.setattr(request_guard, "_limit", lambda: 100)  # 高阈值，不触发 429
    monkeypatch.setattr(request_guard, "_l1_capacity", lambda: 0.0)  # 关 L1，走滑窗
    monkeypatch.setattr(request_guard, "get_client_ip", lambda req: "1.2.3.4")
    # 不应抛
    request_guard.check_rate_limit(_FakeRequest())


def test_storage_adapter_get_does_not_crash_when_none(monkeypatch):
    """get_storage_adapter 在 None 时不抛（async 路径安全调用）。"""
    monkeypatch.setattr(request_guard, "_storage_adapter", None)
    assert request_guard.get_storage_adapter() is None
