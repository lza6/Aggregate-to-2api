"""P1-6 solver 多节点容灾 IdleTimeout 验证（v6.8.0）。

覆盖：
- IdleTimeout=0 永不 idle（向后兼容，默认）；
- IdleTimeout>0：节点空闲超时标记 idle，select_node 优先非 idle 节点；
- 全部 idle 时仍降级用 idle 节点（不阻塞）；
- acquire/release/record 更新 last_activity，活动后 idle 复位；
- select_candidates idle 排序优先级（介于熔断与负载之间）；
- snapshot 暴露 idle 字段（供 /healthz 与 /metrics 消费）。
"""

from __future__ import annotations

import time

from api import config
from api.solver_guard import SolverGuard, SolverNodeState


class TestIdleTimeout:
    def test_disabled_never_idle(self):
        """idle_timeout=0（默认）→ 永不 idle。"""
        n = SolverNodeState("http://s1:8001", idle_timeout=0.0)
        assert n.is_idle() is False

    def test_idle_after_timeout(self, monkeypatch):
        """idle_timeout>0 且空闲超时 → idle=True。"""
        n = SolverNodeState("http://s1:8001", idle_timeout=1.0)
        # 手动把 last_activity 回拨到 2s 前
        n._last_activity_at = time.time() - 2.0
        assert n.is_idle() is True

    def test_activity_resets_idle(self):
        """acquire/release/record 后 last_activity 更新，idle 复位。"""
        n = SolverNodeState("http://s1:8001", idle_timeout=1.0)
        n._last_activity_at = time.time() - 5.0
        assert n.is_idle() is True
        n.acquire_inflight()
        assert n.is_idle() is False  # 活动后复位
        n.release_inflight()
        assert n.is_idle() is False
        n.record_success(1.0)
        assert n.is_idle() is False
        n.record_failure("timeout")
        assert n.is_idle() is False


class TestSelectNodePrefersNonIdle:
    def test_select_prefers_non_idle_node(self):
        """两节点：一 idle 一活跃 → select_node 选非 idle。"""
        g = SolverGuard(urls=["http://a:8001", "http://b:8001"], idle_timeout=1.0)
        g._reset_global_stats()
        a = g._nodes["http://a:8001"]
        b = g._nodes["http://b:8001"]
        # a 空闲超时 idle，b 刚活动过
        a._last_activity_at = time.time() - 5.0
        b._last_activity_at = time.time()
        # 多次选，应总在非 idle 的 b（排除 round-robin 偶发选 a 的可能：a 在 idle 池被排除）
        for _ in range(5):
            selected = g.select_node()
            assert selected is not None
            assert selected.url == "http://b:8001"

    def test_all_idle_still_returns_node(self):
        """所有节点 idle → 降级用 idle 节点（不阻塞）。"""
        g = SolverGuard(urls=["http://a:8001", "http://b:8001"], idle_timeout=1.0)
        for n in g._nodes.values():
            n._last_activity_at = time.time() - 10.0
        selected = g.select_node()
        assert selected is not None  # 不返回 None

    def test_idle_timeout_zero_no_preference_change(self):
        """idle_timeout=0 → 所有节点 non_idle，select_node 退回原加权最少在途逻辑。"""
        g = SolverGuard(urls=["http://a:8001", "http://b:8001"], idle_timeout=0.0)
        # 即便把 last_activity 回拨也不影响（is_idle 永假）
        for n in g._nodes.values():
            n._last_activity_at = time.time() - 100.0
        selected = g.select_node()
        assert selected is not None


class TestSelectCandidatesIdleSort:
    def test_idle_sorts_after_circuit_before_load(self):
        """select_candidates 排序：(circuit, idle, load) — idle 节点排在非 idle 之后。"""
        g = SolverGuard(urls=["http://a:8001", "http://b:8001", "http://c:8001"], idle_timeout=1.0)
        b = g._nodes["http://b:8001"]
        # a: 非 idle；b: idle；c: 非 idle — 排序应 a/c 在前，b 在后
        b._last_activity_at = time.time() - 5.0
        cands = g.select_candidates()
        urls = [n.url for n in cands]
        # a 和 c（非 idle）应在 b（idle）之前
        assert urls.index("http://a:8001") < urls.index("http://b:8001")
        assert urls.index("http://c:8001") < urls.index("http://b:8001")


class TestSnapshotExposesIdle:
    def test_snapshot_has_idle_field(self):
        """snapshot 暴露 idle 字段（供 /healthz 与 /metrics）。"""
        n = SolverNodeState("http://s1:8001", idle_timeout=1.0)
        snap = n.snapshot()
        assert "idle" in snap
        assert snap["idle"] is False  # 刚创建未超时
        n._last_activity_at = time.time() - 5.0
        assert n.snapshot()["idle"] is True


class TestConfigIdleTimeout:
    def test_config_default_zero(self, monkeypatch):
        """默认 IF_SOLVER_IDLE_TIMEOUT_SECONDS=0（向后兼容）。"""
        monkeypatch.setattr(config, "SOLVER_IDLE_TIMEOUT_SECONDS", 0.0)
        # SolverGuard 从 config 读 idle_timeout
        g = SolverGuard(urls=["http://a:8001"])
        for n in g._nodes.values():
            assert n.idle_timeout == 0.0
            assert n.is_idle() is False


class TestIdleFailoverEdgeCases:
    """Critic 补：idle 节点作为 failover 备选 + half-open 探测与 idle 复位交互。"""

    def test_idle_node_still_in_failover_candidates(self):
        """idle 节点仍在 select_candidates 列表内（排末位），可被 failover 选为备选。"""
        g = SolverGuard(urls=["http://a:8001", "http://b:8001"], idle_timeout=1.0)
        b = g._nodes["http://b:8001"]
        b._last_activity_at = time.time() - 5.0
        assert b.is_idle() is True
        cands = g.select_candidates()
        urls = [n.url for n in cands]
        assert "http://b:8001" in urls  # idle 节点仍可被选为备选

    def test_half_open_probe_success_resets_idle(self):
        """idle+熔断节点 half-open 探测成功后 last_activity 复位 → is_idle 变 False。"""
        n = SolverNodeState("http://a:8001", idle_timeout=1.0, circuit_threshold=2)
        # 触发熔断
        n.record_failure("timeout")
        n.record_failure("timeout")
        assert n.circuit_open is True
        # 空闲超时 idle
        n._last_activity_at = time.time() - 5.0
        assert n.is_idle() is True
        # half-open 探测成功（record_success 复位 last_activity + 关熔断）
        n.record_success(1.0)
        assert n.is_idle() is False  # 探测后活动复位
        assert n.circuit_open is False  # 探测成功恢复 CLOSED

