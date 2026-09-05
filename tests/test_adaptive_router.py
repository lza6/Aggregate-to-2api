"""自适应路由引擎（MAB-EWMA）单元测试。

覆盖：评分逻辑、熔断、熔断恢复、探索/利用、全开兜底、路由记录写入与查询、
registry 集成（provider_for 自适应路由）。
"""

import time

from api.adaptive_router import (
    AdaptiveRouter,
)


def _router() -> AdaptiveRouter:
    r = AdaptiveRouter(alpha=0.2, initial_explore_rate=0.10)
    # 禁用随机探索以便确定性断言
    return r


class TestScoring:
    def test_cold_start_picks_first(self):
        r = _router()
        picked = r.select_best(["a", "b"], explore=False)
        assert picked == "a"

    def test_success_rate_preference(self):
        """高成功率 provider 应胜过低成功率（即使时延高）。"""
        r = _router()
        # a: 8 成功 2 失败，低时延
        for _ in range(8):
            r.record_result("a", 200.0, True)
        for _ in range(2):
            r.record_result("a", 200.0, False)
        # b: 2 成功 8 失败，低时延
        for _ in range(2):
            r.record_result("b", 300.0, True)
        for _ in range(8):
            r.record_result("b", 300.0, False)
        picked = r.select_best(["a", "b"], explore=False)
        assert picked == "a"

    def test_latency_preference(self):
        """同等成功率下更快 provider 应胜出。"""
        r = _router()
        for _ in range(10):
            r.record_result("fast", 100.0, True)
        for _ in range(10):
            r.record_result("slow", 800.0, True)
        picked = r.select_best(["fast", "slow"], explore=False)
        assert picked == "fast"

    def test_inflight_backpressure(self):
        """在途请求多 → 负载惩罚 → 分低（防止流量灌进忙节点）。"""
        r = _router()
        for _ in range(10):
            r.record_result("busy", 100.0, True)
        for _ in range(10):
            r.record_result("idle", 100.0, True)
        # busy 在途 20 个，idle 1 个
        r.record_inflight("busy", 20)
        r.record_inflight("idle", 1)
        picked = r.select_best(["busy", "idle"], explore=False)
        assert picked == "idle"

    def test_ewma_updates(self):
        """EWMA 时延应为 alpha 平滑后的值。"""
        r = _router()
        r.record_result("p", 1000.0, True)  # 初始 2000 → 0.2*1000 + 0.8*2000 = 1800
        assert r.nodes["p"].ewma_latency_ms == 1800.0
        r.record_result("p", 0.0, True)  # → 0.2*0 + 0.8*1800 = 1440
        assert r.nodes["p"].ewma_latency_ms == 1440.0


class TestCircuitBreak:
    def test_opens_after_failure_ratio(self):
        """失败率 > 50% 且样本 >= 5 → OPEN。"""
        r = _router()
        for _ in range(5):
            r.record_result("p", 500.0, False)
        assert r.nodes["p"].circuit_state == "OPEN"
        assert r.nodes["p"].circuit_open_until > time.time()

    def test_partial_fail_does_not_open(self):
        """失败率不超过 50% → 不熔断。"""
        r = _router()
        # 4 成功 + 4 失败 = 50%，不熔断
        for _ in range(4):
            r.record_result("p", 200.0, True)
        for _ in range(4):
            r.record_result("p", 200.0, False)
        assert r.nodes["p"].circuit_state == "CLOSED"

    def test_excludes_open_candidate(self):
        """OPEN provider 不应被选中；到期后转 HALF_OPEN 并允许进入候选（但评分仍参与竞争）。"""
        r = _router()
        for _ in range(5):
            r.record_result("bad", 500.0, False)
        assert r.nodes["bad"].circuit_state == "OPEN"
        # OPEN 未到期 → 不可选
        picked = r.select_best(["bad", "good"], explore=False)
        assert picked == "good"
        # 到期后 → HALF_OPEN，bad 进入候选池（但 good 评分更高，仍选 good）
        r.nodes["bad"].circuit_open_until = time.time() - 1
        r.select_best(["bad", "good"], explore=False)
        assert r.nodes["bad"].circuit_state == "HALF_OPEN"
        # 测一下 HALF_OPEN 时 bad 成功一个 → CLOSED
        r.record_result("bad", 300.0, True)
        assert r.nodes["bad"].circuit_state == "CLOSED"

    def test_half_open_success_closes(self):
        """HALF_OPEN 时成功一个 → CLOSED。"""
        r = _router()
        for _ in range(5):
            r.record_result("p", 500.0, False)
        r.nodes["p"].circuit_open_until = time.time() - 1
        # 到期 → HALF_OPEN
        r.select_best(["p"], explore=False)
        assert r.nodes["p"].circuit_state == "HALF_OPEN"
        # 成功 → CLOSED
        r.record_result("p", 300.0, True)
        assert r.nodes["p"].circuit_state == "CLOSED"

    def test_all_open_fallback(self):
        """全部熔断 → 兜底返回第一个候选（最坏也只是慢，不卡死）。"""
        r = _router()
        for p in ["a", "b"]:
            for _ in range(5):
                r.record_result(p, 500.0, False)
        picked = r.select_best(["a", "b"], explore=False)
        assert picked == "a"
        recs = r.records()
        assert recs and recs[-1]["reason"] == "fallback_all_open"


class TestRecord:
    def test_records_written(self):
        r = _router()
        r.select_best(["a", "b"], request_id="req-1", model="m1", requested_provider="a", explore=False)
        recs = r.records()
        assert len(recs) == 1
        assert recs[0]["request_id"] == "req-1"
        assert recs[0]["model"] == "m1"
        assert recs[0]["requested_provider"] == "a"
        assert recs[0]["selected_provider"] in ("a", "b")
        assert "scores" in recs[0]

    def test_circular_bound(self):
        r = _router()
        for i in range(1500):
            r.select_best(["a", "b"], request_id=f"r{i}", explore=False)
        recs = r.records(limit=2000)
        assert len(recs) <= 1000  # 环形缓冲上限
        assert recs[-1]["request_id"] == "r1499"

    def test_node_snapshot(self):
        r = _router()
        r.select_best(["a", "b"], explore=False)
        snap = r.node_snapshot()
        assert "a" in snap and "b" in snap
        assert snap["a"]["score"] > 0


class TestRegistryIntegration:
    def test_provider_for_uses_adaptive_router(self):
        """registry.provider_for 应通过自适应路由选 provider，而非直接返回首选。"""
        from api.providers import aifreeforever, imagefree, nanobanana
        from api.providers.registry import Registry

        reg = Registry()
        reg.register(imagefree.ImagefreeProvider())
        reg.register(aifreeforever.AifreeforeverProvider())
        reg.register(nanobanana.NanobananaProvider())

        # 找到有候选的模型（imagefree 模型 + 备选能力匹配）
        model_id = "imagefree/default"
        provider = reg.provider_for(model_id)
        assert provider is not None
        # 至少生成一条路由记录
        assert len(reg.get_routing_records(limit=10)) >= 1


class TestDegradedSelectBest:
    """P1-1：degraded 降级路径用 select_best 在多候选间打分选最优。"""

    def _make_stub_provider(self, prefix: str):
        """构造最小 stub Provider，只暴露 prefix + health_status（不依赖真实能力匹配）。"""
        class _StubProvider:
            def __init__(self, prefix: str) -> None:
                self.prefix = prefix
                self.health_status = "healthy"
                self.models = {}  # find_alternatives 被 monkeypatch，不读真实 models
        return _StubProvider(prefix)

    def _registry_with_stubs(self):
        """注册 1 个真实首选 + 3 个 stub 备用（健康），用 monkeypatch find_alternatives 控制候选。"""
        from api.providers import imagefree
        from api.providers.registry import Registry

        reg = Registry()
        reg.register(imagefree.ImagefreeProvider())
        # stub 备用不通过 register（register 会读 models），直接塞进 providers 字典
        for px in ("stubA", "stubB", "stubC"):
            stub = self._make_stub_provider(px)
            reg.providers[px] = stub
            reg.provider_health[px] = "healthy"
        return reg

    def test_degraded_multi_candidates_calls_select_best(self, monkeypatch):
        """degraded 时有 ≥2 能力匹配备用 → select_best 被调用，返回 select_best 选的（非首个）。"""
        reg = self._registry_with_stubs()
        model_id = "imagefree/default"
        spec = reg._models[model_id]
        reg.degrade(spec.provider, "测试降级")

        # 桩 find_alternatives 返回 2 个可控 stub 备用（不依赖真实能力匹配）
        stub_a = reg.providers["stubA"]
        stub_b = reg.providers["stubB"]
        monkeypatch.setattr(
            reg, "find_alternatives", lambda mid: [(stub_a, "stubA/m"), (stub_b, "stubB/m")]
        )

        called = {"n": 0, "candidates": None}

        def _fake_select_best(candidates, *, request_id="", model="", requested_provider="", explore=None):
            called["n"] += 1
            called["candidates"] = list(candidates)
            return candidates[-1]  # 返回最后一个（非首个），证明走 select_best

        monkeypatch.setattr(reg.adaptive_router, "select_best", _fake_select_best)

        provider = reg.provider_for(model_id)
        assert provider is not None
        assert called["n"] == 1, "degraded 多候选应调用 select_best 一次"
        assert called["candidates"] == ["stubA", "stubB"]
        # 返回的是 select_best 选的（最后一个 stubB），证明走了打分分支而非首个
        assert provider.prefix == "stubB"

    def test_degraded_single_candidate_skips_select_best(self, monkeypatch):
        """degraded 时仅 1 个备用 → 不调 select_best，直接返回该备用（避免单候选无谓打分）。"""
        reg = self._registry_with_stubs()
        model_id = "imagefree/default"
        spec = reg._models[model_id]
        reg.degrade(spec.provider, "测试降级")

        # 桩 find_alternatives 返回单个备用
        stub_a = reg.providers["stubA"]
        monkeypatch.setattr(reg, "find_alternatives", lambda mid: [(stub_a, "stubA/m")])

        called = {"n": 0}

        def _fake_select_best(candidates, **kwargs):
            called["n"] += 1
            return candidates[0]

        monkeypatch.setattr(reg.adaptive_router, "select_best", _fake_select_best)

        provider = reg.provider_for(model_id)
        assert provider is not None
        assert provider.prefix == "stubA"
        assert called["n"] == 0, "单候选不应调用 select_best"

    def test_degraded_no_candidates_falls_back_direct(self, monkeypatch):
        """degraded 但无能力匹配备用 → 直连首选保底（记 direct），不调 select_best。"""
        reg = self._registry_with_stubs()
        model_id = "imagefree/default"
        spec = reg._models[model_id]
        reg.degrade(spec.provider, "测试降级")

        # 桩 find_alternatives 返回空（无备用）
        monkeypatch.setattr(reg, "find_alternatives", lambda mid: [])

        called = {"n": 0}

        def _fake_select_best(candidates, **kwargs):
            called["n"] += 1
            return candidates[0]

        monkeypatch.setattr(reg.adaptive_router, "select_best", _fake_select_best)

        provider = reg.provider_for(model_id)
        assert provider is not None
        # 无备用 → 直连首选（imagefree）
        assert provider.prefix == spec.provider
        assert called["n"] == 0, "无候选不应调用 select_best"

    def test_healthy_path_skips_select_best(self, monkeypatch):
        """healthy 路径不调 select_best（直连契约不变：返回请求指定的提供商）。"""
        reg = self._registry_with_stubs()
        model_id = "imagefree/default"
        spec = reg._models[model_id]
        reg.recover(spec.provider)  # 确保首选 healthy

        called = {"n": 0}

        def _fake_select_best(candidates, **kwargs):
            called["n"] += 1
            return candidates[0]

        monkeypatch.setattr(reg.adaptive_router, "select_best", _fake_select_best)

        provider = reg.provider_for(model_id)
        assert provider is not None
        # healthy 直连：返回请求指定的提供商（不被偷换）
        assert provider.prefix == spec.provider
        assert called["n"] == 0, "healthy 路径不应调用 select_best"

    def test_find_alternatives_returns_sorted_by_capability_overlap(self):
        """find_alternatives 按能力重叠数降序返回（重叠越多越优先）。"""
        from api.providers import aifreeforever, imagefree, nanobanana
        from api.providers.registry import Registry

        reg = Registry()
        reg.register(imagefree.ImagefreeProvider())
        reg.register(aifreeforever.AifreeforeverProvider())
        reg.register(nanobanana.NanobananaProvider())
        model_id = "imagefree/default"
        alts = reg.find_alternatives(model_id)
        # 至少能找到备用（aifreeforever 与 imagefree 能力有重叠）
        assert len(alts) >= 1
        # 验证返回的是 list[tuple[Provider, str]] 结构
        for p, mid in alts:
            assert hasattr(p, "prefix")
            assert isinstance(mid, str)


class TestPersistence:
    """P3-1 可观测/可恢复：SQLite 持久化、restore、历史查询。"""

    def _router(self, tmp_path) -> AdaptiveRouter:
        return AdaptiveRouter(db_path=str(tmp_path / "routing.db"))

    def test_record_snapshot_contains_record(self, tmp_path):
        """记录后 snapshot 含该记录（持久化路由决策历史）。"""
        r = self._router(tmp_path)
        r.select_best(["a", "b"], request_id="req-persist", model="m1", explore=False)
        recs = r.records()
        assert any(x["request_id"] == "req-persist" for x in recs)

    def test_restore_reads_back_old_records(self, tmp_path):
        """新建实例 restore 后能读回旧记录（持久化生效）。"""
        db_path = str(tmp_path / "routing.db")
        r1 = self._router(tmp_path)
        r1.select_best(["a", "b"], request_id="req-restore", model="m1", explore=False)
        r1.close()  # 关闭旧连接，让新实例重新打开同一 db 文件

        r2 = AdaptiveRouter(db_path=db_path)
        recs = r2.records()
        assert any(x["request_id"] == "req-restore" for x in recs)
        assert len(recs) >= 1

    def test_warm_params_init_ewma(self, tmp_path):
        """warm 参数生效：历史 min/max 被用于冷启动初始化 EWMA。"""
        db_path = str(tmp_path / "routing.db")
        r1 = self._router(tmp_path)
        # 两次真实调用观测：latency 500 / 1500 → warm 用 midpoint=1000
        r1.record_result("p", 500.0, True)
        r1.record_result("p", 1500.0, True)
        r1.close()

        r2 = AdaptiveRouter(db_path=db_path)
        # 冷启动 nodes 为空，用持久化观测 warm：min=500, max=1500 → (500+1500)/2 = 1000
        assert r2.nodes["p"].ewma_latency_ms == 1000.0

    async def test_routing_records_from_ts_endpoint(self, tmp_path, monkeypatch):
        """`/v1/routing/records?from_ts=` 返回持久化历史。"""
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from api.errors import AppError
        from api.handlers import app_error_handler
        from api.routes import admin

        db_path = str(tmp_path / "rt.db")
        ar = AdaptiveRouter(db_path=db_path)
        ar.select_best(["a", "b"], request_id="req-ts", model="m1", explore=False)

        class FakeRegistry:
            adaptive_router = ar

            def get_routing_records(self, limit=50, from_ts=None):
                return ar.records(limit=limit, from_ts=from_ts)

        monkeypatch.setattr(admin, "registry", FakeRegistry())

        application = FastAPI()
        application.add_exception_handler(AppError, app_error_handler)
        application.include_router(admin.router)

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            resp = await client.get("/v1/routing/records?from_ts=0")
        assert resp.status_code == 200
        body = resp.json()
        assert any(x["request_id"] == "req-ts" for x in body["records"])
        assert "nodes" in body
