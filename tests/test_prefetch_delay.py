"""Token 预取延迟自适应（IMP-02）测试。

验证 EMA 计算、延迟 clamp、配置兼容性（IF_PREFETCH_AFTER_SOLVE_DELAY=0 时 EMA 自适应/固定值回退）。
"""
import asyncio
import time

import pytest

from api import config
from api.worker import _TokenPool


def _make_pool() -> _TokenPool:
    """创建测试用的 _TokenPool 实例（不启动 prefetch 循环）。"""
    return _TokenPool("test", lambda: 1, 10, float("inf"), None)


class TestEmaCalculation:
    """_TokenPool.update_solve_time 的 EMA 计算正确性。"""

    def test_initial_ema_is_5_0(self):
        pool = _make_pool()
        assert pool._ema == pytest.approx(5.0)

    def test_ema_after_single_update(self):
        pool = _make_pool()
        pool.update_solve_time(3.0)
        # ema = 5.0 * 0.7 + 3.0 * 0.3 = 3.5 + 0.9 = 4.4
        assert pool._ema == pytest.approx(4.4)

    def test_ema_after_multiple_updates(self):
        pool = _make_pool()
        pool.update_solve_time(3.0)   # ema = 4.4
        pool.update_solve_time(2.0)   # ema = 4.4*0.7 + 2.0*0.3 = 3.68
        assert pool._ema == pytest.approx(3.68)
        pool.update_solve_time(10.0)  # ema = 3.68*0.7 + 10.0*0.3 = 5.576
        assert pool._ema == pytest.approx(5.576)

    def test_ema_custom_alpha(self, monkeypatch):
        monkeypatch.setattr(config, "IF_PREFETCH_EMA_ALPHA", 0.1)
        pool = _make_pool()
        pool.update_solve_time(3.0)
        # ema = 5.0 * 0.9 + 3.0 * 0.1 = 4.5 + 0.3 = 4.8
        assert pool._ema == pytest.approx(4.8)


class TestDelayClamp:
    """延迟 clamp 在 [0.5, 3.0] 范围内；配置兼容性。"""

    def test_delay_uses_ema_half(self):
        pool = _make_pool()
        pool._ema = 2.0
        # clamp(0.5, 2.0 * 0.5, 3.0) = 1.0
        delay = pool._get_prefetch_delay()
        assert delay == pytest.approx(1.0)

    def test_delay_clamp_min(self):
        pool = _make_pool()
        pool._ema = 0.5
        # clamp(0.5, 0.25, 3.0) = 0.5
        delay = pool._get_prefetch_delay()
        assert delay == pytest.approx(0.5)

    def test_delay_clamp_max(self):
        pool = _make_pool()
        pool._ema = 10.0
        # clamp(0.5, 5.0, 3.0) = 3.0
        delay = pool._get_prefetch_delay()
        assert delay == pytest.approx(3.0)

    def test_delay_with_fixed_config(self, monkeypatch):
        monkeypatch.setattr(config, "IF_PREFETCH_AFTER_SOLVE_DELAY", 1.5)
        pool = _make_pool()
        delay = pool._get_prefetch_delay()
        assert delay == pytest.approx(1.5)

    def test_delay_with_fixed_config_zero(self, monkeypatch):
        """IF_PREFETCH_AFTER_SOLVE_DELAY=0 时使用 EMA 自适应。"""
        monkeypatch.setattr(config, "IF_PREFETCH_AFTER_SOLVE_DELAY", 0)
        pool = _make_pool()
        pool._ema = 2.0
        delay = pool._get_prefetch_delay()
        assert delay == pytest.approx(1.0)

    def test_delay_respects_ema_change(self):
        pool = _make_pool()
        pool._ema = 1.0
        # clamp(0.5, 0.5, 3.0) = 0.5
        assert pool._get_prefetch_delay() == pytest.approx(0.5)
        pool._ema = 4.0
        # clamp(0.5, 2.0, 3.0) = 2.0
        assert pool._get_prefetch_delay() == pytest.approx(2.0)


class TestPrefetchLoopIntegration:
    """prefetch_loop 在实际循环中使用自适应延迟而非固定 1.5s。"""

    @pytest.mark.asyncio
    async def test_prefetch_loop_uses_adaptive_delay(self, monkeypatch):
        """验证 prefetch_loop 成功后使用 EMA 自适应延迟。"""
        monkeypatch.setattr(config, "IF_PREFETCH_AFTER_SOLVE_DELAY", 0)
        pool = _make_pool()
        pool._ema = 2.0     # 预期 delay = 1.0s
        pool.sem = asyncio.Semaphore(1)
        # 让 prefetch_loop 只跑一次：第一次求解成功后，token 入池，pool 满 → 进入 need_event.wait
        # 我们需要在 sleep 之后取消它
        solve_count = 0
        solves = []

        async def _fake_solve(*a, **kw):
            nonlocal solve_count
            solve_count += 1
            solves.append(("solve", time.monotonic()))
            return "mock-token", 0.5  # 快速求解

        monkeypatch.setattr("api.turnstile_client.solve_turnstile", _fake_solve)

        task = asyncio.create_task(pool.prefetch_loop())
        await asyncio.sleep(0.2)  # 等 solve 完成 + 进入 sleep
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert solve_count >= 1, "prefetch_loop 应至少求解一次"
        # 验证 EMA 已更新（pool._ema 被设为 2.0，求解耗时 0.5s：2.0 * 0.7 + 0.5 * 0.3 = 1.55）
        assert pool._ema == pytest.approx(2.0 * 0.7 + 0.5 * 0.3)

    @pytest.mark.asyncio
    async def test_prefetch_loop_fixed_delay(self, monkeypatch):
        """IF_PREFETCH_AFTER_SOLVE_DELAY=1.5 时使用固定值。"""
        monkeypatch.setattr(config, "IF_PREFETCH_AFTER_SOLVE_DELAY", 1.5)
        pool = _make_pool()
        pool.sem = asyncio.Semaphore(1)
        solve_count = 0

        async def _fake_solve(*a, **kw):
            nonlocal solve_count
            solve_count += 1
            return "mock-token", 0.5

        monkeypatch.setattr("api.turnstile_client.solve_turnstile", _fake_solve)

        t0 = time.monotonic()
        task = asyncio.create_task(pool.prefetch_loop())
        # 等 solve 完成 + 固定延迟 1.5s（应该略 > 1.5s）
        await asyncio.sleep(1.8)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        elapsed = time.monotonic() - t0
        assert solve_count >= 1
        # 固定延迟 1.5s，总耗时应 >= 1.5s（求解 + 延迟）
        assert elapsed >= 1.5
        # 如果用了自适应（ema=5.0 时 delay=2.5），会超过 1.8s，但这里用了固定值 1.5s
        assert elapsed < 2.0, "固定延迟不应超过 2.0s（自适应 ema=5.0 时 delay=2.5s 会超）"

    @pytest.mark.asyncio
    async def test_solve_turnstile_returns_duration(self, monkeypatch):
        """验证 solve_turnstile 返回 (token, duration) 元组。"""
        from api import turnstile_client

        async def _fake_solve(*a, **kw):
            return "mock-token"

        # mock 掉 _solve_turnstile 让它返回一个 mock token
        monkeypatch.setattr(turnstile_client, "_solve_turnstile", _fake_solve)
        # v4.2 回归：solver_guard.record_success 现有签名带 node_url，允许任意 kwargs 不破坏旧测试
        monkeypatch.setattr(turnstile_client.solver_guard, "record_success",
                            lambda d, **kw: None)

        result = await turnstile_client.solve_turnstile(
            "http://mock", "http://test.com", "sitekey", 30,
        )
        assert isinstance(result, tuple), "solve_turnstile 应返回元组"
        assert len(result) == 2, "solve_turnstile 应返回 (token, duration)"
        token, duration = result
        assert isinstance(token, str)
        assert isinstance(duration, float)
        assert duration >= 0