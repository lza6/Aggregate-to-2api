"""P0-S1（v8.2.3）：request_guard 热路径真接线 Redis 适配器测试。

验收：
- redis 模式（adapter 非 None）下 _l1_check / 基线滑窗真调 adapter.rate_limiter.is_allowed
  （用 Mock 适配器 spy is_allowed 被调用 + 参数正确）。
- adapter 异常时降级到内存分片桶（不 fail-open，保真限流；log.warning 一次）。
- 单机模式（adapter=None）零回归：不调 adapter，走内存桶（与 test_request_guard.py 基线对齐）。
- 同步热路径 → async 适配器桥接正常工作（_await_sync 在无 running loop 时跑 run_until_complete）。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from starlette.requests import Request

import api.request_guard as rg
from api import config
from api.errors import AppError


def _make_request(ip: str) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/generate",
        "raw_path": b"/v1/generate",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"x-forwarded-for", ip.encode()), (b"host", b"testserver"), (b"user-agent", b"pytest")],
        "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8000),
        "state": {},
    }
    return Request(scope)


class _FakeRateLimiter:
    """记录 is_allowed 调用 + 可控行为（allow / deny / raise）。"""

    def __init__(self, *, allow: bool = True, raise_exc: BaseException | None = None) -> None:
        self.calls: list[tuple[str, int, float]] = []
        self._allow = allow
        self._raise = raise_exc

    async def is_allowed(self, key: str, limit: int, window: float = 60.0) -> bool:
        self.calls.append((key, limit, window))
        if self._raise is not None:
            raise self._raise
        return self._allow


class _FakeAdapter:
    """最小适配器：仅暴露 rate_limiter 属性（热路径只用到它）。"""

    def __init__(self, rate_limiter: _FakeRateLimiter) -> None:
        self._rl = rate_limiter

    @property
    def rate_limiter(self) -> _FakeRateLimiter:
        return self._rl

    @property
    def name(self) -> str:
        return "fake-redis"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """每用例：关闭 auto_block + 白名单 + 重置内存状态 + 清 adapter。"""
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_ENABLED", False)
    monkeypatch.setattr(config, "IF_IP_WHITELIST", "")
    rg.set_storage_adapter(None)
    rg.reset_runtime_state()
    yield
    rg.set_storage_adapter(None)
    rg.reset_runtime_state()
    # 清线程局部 loop 残留，避免跨用例复用已关闭 loop
    loop = getattr(rg._loop_local, "loop", None)
    if loop is not None:
        try:
            loop.close()
        except Exception:
            pass
        rg._loop_local.loop = None


# ── L1 令牌桶热路径真调适配器 ──────────────────────────────


class TestL1RedisHotPath:
    def test_l1_check_calls_adapter_when_present(self, monkeypatch):
        """adapter 非 None → _l1_check 调 adapter.rate_limiter.is_allowed（key/limit/window 正确）。"""
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 5.0)
        monkeypatch.setattr(config, "IF_RATE_TOKEN_REFILL_PER_SEC", 0.0)  # refill=0 → window=cap
        rl = _FakeRateLimiter(allow=True)
        rg.set_storage_adapter(_FakeAdapter(rl))
        assert rg._l1_check("1.2.3.4", time.time()) is True
        assert len(rl.calls) == 1
        key, limit, window = rl.calls[0]
        assert key == "l1:1.2.3.4"
        assert limit == 5
        assert window == 5.0  # max(capacity, 1.0)

    def test_l1_check_adapter_deny_returns_false(self, monkeypatch):
        """adapter is_allowed 返回 False → _l1_check 返回 False（超桶）。"""
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 3.0)
        monkeypatch.setattr(config, "IF_RATE_TOKEN_REFILL_PER_SEC", 0.0)
        rl = _FakeRateLimiter(allow=False)
        rg.set_storage_adapter(_FakeAdapter(rl))
        assert rg._l1_check("5.6.7.8", time.time()) is False

    def test_l1_check_adapter_exception_falls_back_to_memory(self, monkeypatch):
        """adapter 异常 → 降级内存桶；返回值由内存桶决定（这里 allow=True 故内存桶有 token 放行）。"""
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 2.0)
        monkeypatch.setattr(config, "IF_RATE_TOKEN_REFILL_PER_SEC", 0.0)
        rl = _FakeRateLimiter(raise_exc=RuntimeError("redis down"))
        rg.set_storage_adapter(_FakeAdapter(rl))
        # 内存桶首请求应放行（capacity=2，首扣 1）
        assert rg._l1_check("9.9.9.9", time.time()) is True
        assert len(rl.calls) == 1  # 调了一次才失败

    def test_l1_refill_positive_uses_thin_window(self, monkeypatch):
        """refill>0 时窗口=capacity/refill（细窗补满一次令牌）。"""
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 10.0)
        monkeypatch.setattr(config, "IF_RATE_TOKEN_REFILL_PER_SEC", 2.0)  # window=10/2=5s
        rl = _FakeRateLimiter(allow=True)
        rg.set_storage_adapter(_FakeAdapter(rl))
        rg._l1_check("1.1.1.1", time.time())
        assert rl.calls[0][2] == 5.0  # 10/2

    def test_l1_check_no_adapter_uses_memory_bucket(self, monkeypatch):
        """adapter=None → 走内存桶（零回归）；首请求放行。"""
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 1.0)
        monkeypatch.setattr(config, "IF_RATE_TOKEN_REFILL_PER_SEC", 0.0)
        rg.set_storage_adapter(None)
        assert rg._l1_check("2.2.2.2", time.time()) is True
        # 第二次应超桶
        assert rg._l1_check("2.2.2.2", time.time()) is False

    def test_check_generate_request_l1_uses_adapter(self, monkeypatch):
        """端到端：check_generate_request 在 redis 模式下经 _l1_check 调适配器。"""
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 2.0)
        monkeypatch.setattr(config, "IF_RATE_TOKEN_REFILL_PER_SEC", 0.0)
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)  # 关滑窗，只测 L1
        rl = _FakeRateLimiter(allow=True)
        rg.set_storage_adapter(_FakeAdapter(rl))
        rg.check_generate_request(_make_request("3.3.3.3"))
        assert any(c[0] == "l1:3.3.3.3" for c in rl.calls)


# ── 基线滑窗热路径真调适配器 ───────────────────────────────


class TestSlidingWindowRedisHotPath:
    def test_sliding_window_calls_adapter_when_present(self, monkeypatch):
        """adapter 非 None + L1 关闭 → 基线滑窗调 adapter.is_allowed(rate:key)。"""
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 0.0)  # 关 L1
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 10)
        rl = _FakeRateLimiter(allow=True)
        rg.set_storage_adapter(_FakeAdapter(rl))
        rg.check_rate_limit(_make_request("4.4.4.4"))
        assert any(c[0] == "rate:4.4.4.4" and c[1] == 10 for c in rl.calls)

    def test_sliding_window_adapter_deny_raises_429(self, monkeypatch):
        """adapter is_allowed=False → check_rate_limit 抛 429。"""
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 0.0)
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 1)
        rl = _FakeRateLimiter(allow=False)
        rg.set_storage_adapter(_FakeAdapter(rl))
        with pytest.raises(AppError) as exc:
            rg.check_rate_limit(_make_request("5.5.5.5"))
        assert exc.value.status_code == 429

    def test_sliding_window_adapter_exception_falls_back_memory(self, monkeypatch):
        """adapter 异常 → 降级内存滑窗（首请求放行，不 fail-open 也不 crash）。"""
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 0.0)
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 5)
        rl = _FakeRateLimiter(raise_exc=ConnectionError("redis down"))
        rg.set_storage_adapter(_FakeAdapter(rl))
        # 降级后走内存滑窗，首请求放行
        rg.check_rate_limit(_make_request("6.6.6.6"))

    def test_sliding_window_no_adapter_uses_memory(self, monkeypatch):
        """adapter=None → 走内存滑窗（与 v7.x 行为一致）。"""
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 0.0)
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 2)
        rg.set_storage_adapter(None)
        req = _make_request("7.7.7.7")
        rg.check_rate_limit(req)
        rg.check_rate_limit(req)
        with pytest.raises(AppError) as exc:
            rg.check_rate_limit(req)
        assert exc.value.status_code == 429

    def test_sliding_window_limit_zero_skips_adapter(self, monkeypatch):
        """limit<=0（关闭滑窗）→ 不调 adapter，直接 return（不污染决策）。"""
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 0.0)
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)
        rl = _FakeRateLimiter(allow=True)
        rg.set_storage_adapter(_FakeAdapter(rl))
        rg.check_rate_limit(_make_request("8.8.8.8"))
        assert len(rl.calls) == 0  # 关闭滑窗，不调


# ── 降级 warning 去重 ──────────────────────────────────────


class TestFallbackWarning:
    def test_fallback_warned_once_per_mount(self, monkeypatch):
        """同一轮装配内多次异常仅 warning 一次；set_storage_adapter 重置标志。"""
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 1.0)
        monkeypatch.setattr(config, "IF_RATE_TOKEN_REFILL_PER_SEC", 0.0)
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)
        rl = _FakeRateLimiter(raise_exc=RuntimeError("down"))
        rg.set_storage_adapter(_FakeAdapter(rl))
        # 触发多次降级
        rg._l1_check("a", time.time())
        rg._l1_check("b", time.time())
        rg._l1_check("c", time.time())
        assert rg._redis_fallback_warned is True


# ── async 上下文同步桥接（_await_sync 子线程路径）────────────


class TestAwaitSyncAsyncContext:
    def test_await_sync_in_running_loop_uses_subthread(self):
        """当前线程已有 running loop 时 _await_sync 起子线程跑，不阻塞主 loop。"""

        async def main():
            # 主线程有 running loop
            result = rg._await_sync(_sample_coro(42))
            return result

        result = asyncio.run(main())
        assert result == 42

    def test_await_sync_no_running_loop_uses_local_loop(self):
        """无 running loop（普通 sync 上下文）→ 复用线程局部 loop。"""
        result = rg._await_sync(_sample_coro("ok"))
        assert result == "ok"

    def test_await_sync_propagates_exception(self):
        """协程异常向上抛，由调用方降级。"""

        async def boom():
            raise ConnectionError("redis gone")

        with pytest.raises(ConnectionError):
            rg._await_sync(boom())


async def _sample_coro(val: Any) -> Any:
    await asyncio.sleep(0)
    return val
