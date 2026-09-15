"""v15-B：统一 CAPTCHA/CF 求解结果协议（CaptchaResult）单元测试。

覆盖：ok 语义、from_turnstile / from_cf_clearance 两个工厂映射、
solve_turnstile_result 成功（mock 8001 返回 value）与失败（captcha_fail → 异常）路径、
solve_result 对 dict/None 两态、以及向后兼容（solve_turnstile 仍 tuple[str,float]、
CfClearanceSolver.solve 仍 dict）。全部 Mock（fake client / httpx.MockTransport），
零真实上游调用。
"""

from dataclasses import FrozenInstanceError

import httpx
import pytest

from api import turnstile_client
from api.captcha.protocol import (
    CF_CLEARANCE_SOLVER,
    TURNSTILE_SOLVER,
    CaptchaResult,
    from_cf_clearance,
    from_turnstile,
)
from api.cf_clearance_solver import CfClearanceSolver
from api.solver_guard import SolverGuard


# ── CaptchaResult 语义 ─────────────────────────────────
class TestCaptchaResultSemantics:
    def test_ok_semantics(self) -> None:
        # 默认空结果 → ok=False
        empty = CaptchaResult()
        assert empty.ok is False
        assert empty.token == ""
        assert empty.cookies == []
        assert empty.user_agent == ""
        assert empty.elapsed_ms == 0.0
        assert empty.solver == ""
        # token 非空 → ok=True；显式空 token → ok=False
        assert CaptchaResult(token="tok").ok is True
        assert CaptchaResult(token="").ok is False

    def test_frozen_immutable(self) -> None:
        r = CaptchaResult(token="tok")
        with pytest.raises(FrozenInstanceError):
            r.token = "other"  # type: ignore[misc]


# ── 工厂映射 ───────────────────────────────────────────
class TestFactories:
    def test_from_turnstile_maps_token_elapsed_solver(self) -> None:
        r = from_turnstile("tok-1", 250.0)
        assert r.token == "tok-1"
        assert r.elapsed_ms == 250.0
        assert r.solver == TURNSTILE_SOLVER
        assert r.ok is True
        assert r.cookies == []

    def test_from_turnstile_empty_token_not_ok(self) -> None:
        r = from_turnstile("")
        assert r.ok is False
        assert r.token == ""
        assert r.solver == TURNSTILE_SOLVER

    def test_from_cf_clearance_none_returns_empty_not_ok(self) -> None:
        r = from_cf_clearance(None)
        assert r.ok is False
        assert r.token == ""
        assert r.cookies == []
        assert r.user_agent == ""
        assert r.elapsed_ms == 0.0
        assert r.solver == CF_CLEARANCE_SOLVER

    def test_from_cf_clearance_empty_dict_not_ok(self) -> None:
        assert from_cf_clearance({}).ok is False

    def test_from_cf_clearance_maps_fields(self) -> None:
        d = {
            "cf_clearance": "clr-abc",
            "cookies": [{"name": "cf_clearance", "value": "clr-abc"}],
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "elapsed_ms": 12.5,
        }
        r = from_cf_clearance(d)
        assert r.ok is True
        assert r.token == "clr-abc"
        assert r.cookies == [{"name": "cf_clearance", "value": "clr-abc"}]
        assert r.user_agent.startswith("Mozilla/5.0")
        assert r.elapsed_ms == 12.5
        assert r.solver == CF_CLEARANCE_SOLVER


# ── turnstile 通道（fake client，Mock 8001）─────────────
class _Resp:
    def __init__(self, status_code, body) -> None:
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


class _FakeClient:
    def __init__(self, results=None) -> None:
        self._results = list(results or [])

    async def get(self, url, params=None, timeout=None):
        if "/turnstile" in url:
            return _Resp(202, {"task_id": "t1", "status": "accepted"})
        if self._results:
            return self._results.pop(0)
        return _Resp(202, {"status": "pending"})


def _patch_solver(monkeypatch, fake_client) -> SolverGuard:
    g = SolverGuard(circuit_threshold=2)
    monkeypatch.setattr(turnstile_client, "solver_guard", g)
    monkeypatch.setattr(turnstile_client, "_get_client", lambda: fake_client)
    return g


class TestSolveTurnstileResult:
    @pytest.mark.asyncio
    async def test_success_returns_captcha_result(self, monkeypatch) -> None:
        fc = _FakeClient(results=[_Resp(200, {"status": "success", "value": "tok-1"})])
        _patch_solver(monkeypatch, fc)
        r = await turnstile_client.solve_turnstile_result("http://solver:8001", "http://t/x", "sk", 5.0)
        assert r.ok is True
        assert r.token == "tok-1"
        assert r.solver == TURNSTILE_SOLVER
        assert r.elapsed_ms >= 0
        assert r.cookies == []
        assert r.user_agent == ""

    @pytest.mark.asyncio
    async def test_captcha_fail_raises(self, monkeypatch) -> None:
        fc = _FakeClient(results=[_Resp(200, {"status": "success", "value": "captcha_fail"})])
        g = _patch_solver(monkeypatch, fc)
        with pytest.raises(turnstile_client.TurnstileError):
            await turnstile_client.solve_turnstile_result("http://solver:8001", "http://t/x", "sk", 5.0)
        assert g.snapshot()["failure_reasons"] == {"solver_rejected": 1}

    @pytest.mark.asyncio
    async def test_backward_compat_solve_turnstile_tuple(self, monkeypatch) -> None:
        fc = _FakeClient(results=[_Resp(200, {"status": "success", "value": "tok-1"})])
        _patch_solver(monkeypatch, fc)
        tok, dur = await turnstile_client.solve_turnstile("http://solver:8001", "http://t/x", "sk", 5.0)
        assert isinstance(tok, str)
        assert tok == "tok-1"
        assert isinstance(dur, float)
        assert dur >= 0


# ── cf_clearance 通道（httpx.MockTransport，零网络）──────
class TestSolveResult:
    _ALPHABET = "VoT5ZdADLMvIqragNp+EJCPt64$Xm9i8OzcRnx7uysWFBG2Qw-eYjkbK1l3hSf0UH"
    _JSD_PATH = "a2fed62c/0.0.0.0:1234567890:abcdef"

    def _make_solver(self, handler) -> CfClearanceSolver:
        solver = CfClearanceSolver()
        solver._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return solver

    def _challenge_handler(self, main_js: str):
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if url == "https://example.com/":
                return httpx.Response(
                    403,
                    headers={"cf-ray": "a2fed62cef4e48f6-HKG"},
                    text='<html data-ray="a2fed62cef4e48f6">challenge</html>',
                )
            if "main.js" in url:
                return httpx.Response(200, text=main_js)
            if "oneshot" in url:
                resp = httpx.Response(200)
                resp.headers["set-cookie"] = "cf_clearance=clr-abc; Path=/; Domain=.example.com"
                return resp
            return httpx.Response(404)

        return handler

    @pytest.mark.asyncio
    async def test_solve_result_success_maps_fields(self) -> None:
        main_js = f'var x="{self._ALPHABET}";var y="{self._JSD_PATH}";'
        solver = self._make_solver(self._challenge_handler(main_js))
        try:
            r = await solver.solve_result("https://example.com/")
            assert r.ok is True
            assert r.token == "clr-abc"
            assert r.solver == CF_CLEARANCE_SOLVER
            assert r.user_agent
            assert r.elapsed_ms >= 0
            assert any(c["name"] == "cf_clearance" for c in r.cookies)
        finally:
            await solver.close()

    @pytest.mark.asyncio
    async def test_solve_result_none_returns_not_ok(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, text="<html>no ray here</html>")

        solver = self._make_solver(handler)
        try:
            r = await solver.solve_result("https://example.com/")
            assert r.ok is False
            assert r.token == ""
            assert r.cookies == []
            assert r.solver == CF_CLEARANCE_SOLVER
        finally:
            await solver.close()

    @pytest.mark.asyncio
    async def test_backward_compat_solve_returns_dict(self) -> None:
        main_js = f'var x="{self._ALPHABET}";var y="{self._JSD_PATH}";'
        solver = self._make_solver(self._challenge_handler(main_js))
        try:
            d = await solver.solve("https://example.com/")
            assert isinstance(d, dict)
            assert d["cf_clearance"] == "clr-abc"
            assert "elapsed_ms" in d
        finally:
            await solver.close()
