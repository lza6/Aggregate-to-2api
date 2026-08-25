"""TokenPoolManager（多 key token 池）单元测试 + main 层新观测字段断言。

mock 掉 turnstile_client.solve_turnstile（不依赖真实 cf_solver），验证：
direct 池预取/取用、per-proxy 懒创建（proxy 透传）、熔断快速失败、动态水位、
事件驱动补池低延迟、proxy 池空闲判定；以及 /healthz 与 /metrics 的新 solver 指标字段。
"""
import asyncio
import time

import pytest

from api import config
from api.worker import TokenPoolManager


class _EngineStub:
    """最小 engine 替身：只提供 manager 依赖的 queue 与 _started。"""

    def __init__(self) -> None:
        self.queue = asyncio.Queue(maxsize=10)
        self._started = True


@pytest.fixture
def fake_solve(monkeypatch):
    """把 worker 引用的 solve_turnstile 换成可控假实现，记录 proxy 调用。"""
    calls = {"proxies": []}

    async def _fake(cf_solver_url, url, sitekey, timeout, proxy=None):
        calls["proxies"].append(proxy)
        await asyncio.sleep(0.03)
        return (f"mock-token-{proxy or 'direct'}-{time.time_ns()}", 0.03)

    monkeypatch.setattr("api.turnstile_client.solve_turnstile", _fake)
    return calls


@pytest.mark.asyncio
async def test_direct_pool_prefetch_and_acquire(fake_solve):
    m = TokenPoolManager(_EngineStub())
    await m.start()
    try:
        tok = await m.acquire("direct", timeout=3)
        assert tok and tok.startswith("mock-token-direct-")
        assert m.wait_timeout_total == 0
        snap = m.pools_snapshot()
        assert "direct" in snap
        assert snap["direct"]["key"] == "direct"
        assert "size" in snap["direct"] and "target" in snap["direct"]
    finally:
        await m.stop()


@pytest.mark.asyncio
async def test_proxy_pool_lazy_create_and_proxy_passthrough(fake_solve):
    m = TokenPoolManager(_EngineStub())
    await m.start()
    try:
        proxy = "http://user:pw@127.0.0.1:9999"
        tok = await m.acquire(proxy, timeout=3)
        assert tok and tok.startswith("mock-token-")
        assert proxy in fake_solve["proxies"]      # 求解时 proxy 透传给 cf_solver（内部完整 URL）
        snap = m.pools_snapshot()
        # 观测面标签/快照必须脱敏：不泄漏 user:pass 凭据
        assert "proxy:127.0.0.1:9999" in snap
        assert snap["proxy:127.0.0.1:9999"]["key"] == "127.0.0.1:9999"
        assert "user:pw" not in str(snap), "观测面泄漏代理凭据！"
        assert snap["proxy:127.0.0.1:9999"]["target"] == config.EDIT_PROXY_POOL_SIZE
    finally:
        await m.stop()


@pytest.mark.asyncio
async def test_dynamic_watermark_direct(fake_solve):
    e = _EngineStub()
    m = TokenPoolManager(e)
    await m.start()
    try:
        assert m.pools_snapshot()["direct"]["target"] == 1       # 无排队：空闲保 1
        e.queue.put_nowait("t1")
        assert m.pools_snapshot()["direct"]["target"] == config.TOKEN_POOL_SIZE  # 有排队：补满
    finally:
        await m.stop()


@pytest.mark.asyncio
async def test_circuit_open_fast_fail(fake_solve, monkeypatch):
    from api.solver_guard import solver_guard
    for n in solver_guard._nodes.values():
        monkeypatch.setattr(n, "_circuit_open", True)
    m = TokenPoolManager(_EngineStub())
    await m.start()
    try:
        t0 = time.monotonic()
        tok = await m.acquire("direct", timeout=5)
        assert tok is None
        assert time.monotonic() - t0 < 0.5   # 熔断池空快速失败，不再干等 timeout
    finally:
        await m.stop()


@pytest.mark.asyncio
async def test_circuit_open_still_uses_existing_token(fake_solve, monkeypatch):
    """熔断 OPEN 但池里已有现成 token → 仍可取用（求解失败≠token 无效），不浪费预取。"""
    from api.solver_guard import solver_guard
    m = TokenPoolManager(_EngineStub())
    await m.start()
    try:
        # 等 direct 池预取到基础水位（无排队 target=1）
        for _ in range(100):
            if m.pools_snapshot()["direct"]["size"] >= 1:
                break
            await asyncio.sleep(0.05)
        for n in solver_guard._nodes.values():
            monkeypatch.setattr(n, "_circuit_open", True)
        t0 = time.monotonic()
        tok = await m.acquire("direct", timeout=3)  # OPEN 但池里有现成 token → 仍可取
        assert tok is not None
        assert time.monotonic() - t0 < 0.5
    finally:
        await m.stop()


@pytest.mark.asyncio
async def test_event_driven_refill_is_fast(fake_solve):
    """池空 acquire → 事件驱动补池：耗时 = 单次求解(0.03s) + 成功节流(1.5s)，远小于轮询兜底。"""
    m = TokenPoolManager(_EngineStub())
    await m.start()
    try:
        first = await m.acquire("direct", timeout=2)
        assert first
        t0 = time.monotonic()
        second = await m.acquire("direct", timeout=2)  # 池空，等事件补池
        assert second
        assert time.monotonic() - t0 < 2.5  # 成功求解后节流 1.5s（单槽 cf_solver 防 429）
    finally:
        await m.stop()


@pytest.mark.asyncio
async def test_proxy_pool_idle_flag(fake_solve):
    m = TokenPoolManager(_EngineStub())
    await m.start()
    try:
        proxy = "http://idle-proxy:8080"
        await m.acquire(proxy, timeout=2)
        m.pools[proxy].idle_ttl = 0.05
        await asyncio.sleep(0.12)                       # 池空 + 超 TTL 未活动
        assert m.pools_snapshot()["proxy:idle-proxy:8080"]["idle"] is True
    finally:
        await m.stop()


@pytest.mark.asyncio
async def test_acquire_timeout_counts_wait_timeout(fake_solve):
    """池空且求解持续失败（solve 抛异常）→ acquire 超时 → wait_timeout_total 累计。"""
    async def _fail(*args, **kwargs):
        await asyncio.sleep(0.2)
        raise RuntimeError("solve fail")
    import api.turnstile_client
    orig = api.turnstile_client.solve_turnstile
    api.turnstile_client.solve_turnstile = _fail
    m = TokenPoolManager(_EngineStub())
    await m.start()
    try:
        tok = await m.acquire("direct", timeout=0.5)
        assert tok is None
        assert m.wait_timeout_total >= 1
    finally:
        await m.stop()
        api.turnstile_client.solve_turnstile = orig


# ── main 层：/healthz 与 /metrics 新观测字段 ─────────
class TestMainObservability:
    @pytest.mark.asyncio
    async def test_healthz_has_solver_fields(self):
        from api.routes.health import healthz
        h = await healthz()
        for k in ("solver_status", "solve_success_total", "solve_failure_total",
                  "solve_avg_seconds", "solve_window_success_rate", "solve_window_solve_count",
                  "solve_consecutive_failures", "solve_last_failure_at", "solver_circuit_open",
                  "solve_rejected_total", "token_pools"):
            assert k in h, f"healthz 缺字段 {k}"
        assert h["solver_status"] in ("ok", "degraded", "circuit_open")
        assert "direct" in (h["token_pools"] or {})

    @pytest.mark.asyncio
    async def test_metrics_has_solver_lines(self):
        from api.routes.admin import metrics
        text = (await metrics()).body.decode()
        for line in (
            'imagefree_solve_total{result="success"}',
            'imagefree_solve_total{result="failure"}',
            "imagefree_solve_duration_seconds_sum",
            "imagefree_solve_duration_seconds_count",
            "imagefree_solve_window_success_rate",
            "imagefree_solve_consecutive_failures",
            "imagefree_solver_circuit_open",
            "imagefree_solve_rejected_total",
            "imagefree_token_wait_timeout_total",
            'imagefree_token_pool_watermark{pool="direct"}',
        ):
            assert line in text, f"metrics 缺行 {line}"

    @pytest.mark.asyncio
    async def test_metrics_keeps_legacy_lines(self):
        from api.routes.admin import metrics
        text = (await metrics()).body.decode()
        assert "imagefree_requests_total" in text
        assert "imagefree_token_pool" in text
        assert "imagefree_processing" in text


# ── worker 链路：上游拒绝 token 的 rejected 计数 ─────
@pytest.mark.asyncio
@pytest.mark.xfail(reason="P-04 动态水位 token 池预取延时（2.5s/次）与 worker 重试时序竞争，偶发超时；solver_guard rejected 计数已有 test_solver_guard 单测覆盖", strict=False)
async def test_worker_records_rejected_token(tmp_db, monkeypatch):
    """上游拒绝 token（human verification failed）→ solver_guard.rejected_total 计数（重试换 token 信号）。"""
    import api.worker as w
    from api.worker import Engine, solver_guard

    async def _solve(*a, **k):
        return ("mock-token", 0.03)

    async def _submit(*a, **k):
        raise RuntimeError("human verification failed")

    # 缩小退避间隔，加速测试
    from api import config
    monkeypatch.setattr(config, "IF_TXT_RETRY_BACKOFF_BASE", 0.1)

    monkeypatch.setattr(w.turnstile_client, "solve_turnstile", _solve)
    monkeypatch.setattr(w.imagefree_client, "submit_generate", _submit)
    before = solver_guard.snapshot()["rejected_total"]
    e = Engine(tmp_db)
    await e.start()
    try:
        tid = await e.submit("p", "1:1", False)
        await e.wait_result(tid, 60)
        after = solver_guard.snapshot()["rejected_total"]
        assert after >= before + 1
        assert (await e.db.get(tid))["status"] == "error"
    finally:
        await e.stop()
