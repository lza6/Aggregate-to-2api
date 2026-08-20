"""turnstile_client（cf_solver 客户端）单元测试。

覆盖：求解成功路径、202 轮询、终态错误（404/408/422）、captcha_fail 拒绝、
TransportError 重试、创建任务非 202、缺 task_id、超时、
solver_guard 熔断协作（成功/失败/拒绝对应上报路径）、proxy 透传参数。
所有 HTTP 用可编程 fake client monkeypatch，不碰真实网络。
"""
import asyncio
import time

import httpx
import pytest

from api import turnstile_client
from api.solver_guard import SolverGuard


def _patch_solve(monkeypatch, fake_client):
    import api.solver_guard
    g = SolverGuard(circuit_threshold=2)
    monkeypatch.setattr(turnstile_client, "solver_guard", g)
    monkeypatch.setattr(turnstile_client, "_get_client", lambda: fake_client)
    return g


class _Resp:
    def __init__(self, status_code, body) -> None:
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


class _FakeClient:
    def __init__(self, create=None, results=None) -> None:
        # create: callable -> (status, body)；results: 依次返回的 result 响应
        self._create = create or (lambda: (202, {"task_id": "t1", "status": "accepted"}))
        self._results = list(results or [])
        self.create_params = None
        self.result_params = None

    async def get(self, url, params=None, timeout=None):
        if "/turnstile" in url:
            self.create_params = params
            st, body = self._create()
            return _Resp(st, body)
        self.result_params = params
        if self._results:
            item = self._results.pop(0)
            if isinstance(item, BaseException):
                raise item
            elif isinstance(item, type) and issubclass(item, BaseException):
                raise item()
            return item
        return _Resp(202, {"status": "pending"})


# ── 成功路径 ───────────────────────────────────────
class TestSolveSuccess:
    @pytest.mark.asyncio
    async def test_success_returns_token_and_duration(self, monkeypatch):
        g = _patch_solve(monkeypatch, _FakeClient(results=[_Resp(200, {"status": "success", "value": "tok-1"})]))
        tok, dur = await turnstile_client.solve_turnstile("http://solver", "http://t/x", "sk", 5.0)
        assert tok == "tok-1"
        assert dur >= 0
        snap = g.snapshot()
        assert snap["solve_success_total"] == 1
        assert snap["solver_status"] == "ok"

    @pytest.mark.asyncio
    async def test_create_task_passes_proxy_param(self, monkeypatch):
        fc = _FakeClient(results=[_Resp(200, {"status": "success", "value": "tok"})])
        _patch_solve(monkeypatch, fc)
        await turnstile_client.solve_turnstile("http://solver", "http://t/x", "sk", 5.0, proxy="http://p:1")
        assert fc.create_params.get("proxy") == "http://p:1"

    @pytest.mark.asyncio
    async def test_create_task_no_proxy_param(self, monkeypatch):
        fc = _FakeClient(results=[_Resp(200, {"status": "success", "value": "tok"})])
        _patch_solve(monkeypatch, fc)
        await turnstile_client.solve_turnstile("http://solver", "http://t/x", "sk", 5.0, proxy=None)
        assert "proxy" not in fc.create_params


# ── 轮询终态 ───────────────────────────────────────
class TestSolveErrors:
    @pytest.mark.asyncio
    async def test_captcha_fail_rejected(self, monkeypatch):
        fc = _FakeClient(results=[_Resp(200, {"status": "success", "value": "captcha_fail"})])
        g = _patch_solve(monkeypatch, fc)
        with pytest.raises(turnstile_client.TurnstileError):
            await turnstile_client.solve_turnstile("http://solver", "http://t/x", "sk", 5.0)
        assert g.snapshot()["failure_reasons"] == {"solver_rejected": 1}

    @pytest.mark.asyncio
    async def test_terminal_http_error_404(self, monkeypatch):
        fc = _FakeClient(results=[_Resp(404, {"status": "expired"})])
        g = _patch_solve(monkeypatch, fc)
        with pytest.raises(turnstile_client.TurnstileError):
            await turnstile_client.solve_turnstile("http://solver", "http://t/x", "sk", 5.0)
        assert g.snapshot()["failure_reasons"] == {"http_error": 1}

    @pytest.mark.asyncio
    async def test_terminal_http_error_422(self, monkeypatch):
        fc = _FakeClient(results=[_Resp(422, {"status": "failed"})])
        _patch_solve(monkeypatch, fc)
        with pytest.raises(turnstile_client.TurnstileError):
            await turnstile_client.solve_turnstile("http://solver", "http://t/x", "sk", 5.0)

    @pytest.mark.asyncio
    async def test_create_task_non_202_raises(self, monkeypatch):
        fc = _FakeClient(create=lambda: (503, {"error": "down"}), results=[])
        _patch_solve(monkeypatch, fc)
        with pytest.raises(turnstile_client.TurnstileError, match="503"):
            await turnstile_client.solve_turnstile("http://solver", "http://t/x", "sk", 5.0)

    @pytest.mark.asyncio
    async def test_missing_task_id_raises(self, monkeypatch):
        fc = _FakeClient(create=lambda: (202, {}), results=[])
        _patch_solve(monkeypatch, fc)
        with pytest.raises(turnstile_client.TurnstileError, match="task_id"):
            await turnstile_client.solve_turnstile("http://solver", "http://t/x", "sk", 5.0)


# ── 超时 / 重试 ────────────────────────────────────
class TestTimeoutRetry:
    @pytest.mark.asyncio
    async def test_poll_timeout(self, monkeypatch):
        """持续 pending 超过超时 → TimeoutError，上报 timeout。"""
        fc = _FakeClient(results=[_Resp(202, {"status": "pending"}), _Resp(202, {"status": "pending"})])
        g = _patch_solve(monkeypatch, fc)
        monkeypatch.setattr(turnstile_client, "POLL_INTERVAL", 0.02)
        with pytest.raises(TimeoutError):
            await turnstile_client.solve_turnstile("http://solver", "http://t/x", "sk", timeout=0.1)
        assert g.snapshot()["failure_reasons"] == {"timeout": 1}

    @pytest.mark.asyncio
    async def test_transport_error_retries_then_succeeds(self, monkeypatch):
        fc = _FakeClient(results=[_raise_transport(), _Resp(200, {"status": "success", "value": "tok"})])
        g = _patch_solve(monkeypatch, fc)
        monkeypatch.setattr(turnstile_client, "POLL_INTERVAL", 0.01)
        tok, _ = await turnstile_client.solve_turnstile("http://solver", "http://t/x", "sk", 5.0)
        assert tok == "tok"
        assert g.snapshot()["solve_success_total"] == 1

    @pytest.mark.asyncio
    async def test_transport_error_retries_then_425_syntax_guarded(self, monkeypatch):
        """TransportError 不吞掉后续终态：重试 → 422 → http_error 上报。"""
        fc = _FakeClient(results=[_raise_transport(), _Resp(422, {"status": "failed"})])
        g = _patch_solve(monkeypatch, fc)
        monkeypatch.setattr(turnstile_client, "POLL_INTERVAL", 0.01)
        with pytest.raises(turnstile_client.TurnstileError):
            await turnstile_client.solve_turnstile("http://solver", "http://t/x", "sk", 5.0)
        assert set(g.snapshot()["failure_reasons"]) == {"http_error"}


def _raise_transport():
    return httpx.TransportError("boom")