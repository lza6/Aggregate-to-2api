"""M5-E1 补测：solver_guard 熔断恢复、节点选取、集群全熔断等缺失分支。

覆盖 api/solver_guard.py 缺失行（_reset、configure_nodes 兼容、select_candidates、
circuit_open/consecutive_failures 集群聚合、record_success/failure 不指定 node_url 等）。
"""

from __future__ import annotations

import time

from api.solver_guard import SolverGuard, SolverNodeState


def test_reset_clears_all_state():
    """_reset 清空全局统计与各节点状态。"""
    g = SolverGuard(circuit_threshold=3, urls=["http://s1:8001"])
    g.record_success(1.0)
    g.record_failure("timeout", 1.0)
    g.record_rejected()
    assert g.snapshot()["solve_total"] > 0
    g._reset()
    s = g.snapshot()
    assert s["solve_total"] == 0
    assert s["rejected_total"] == 0
    assert s["solve_failure_total"] == 0


def test_configure_nodes_dedup_and_weight_update():
    """configure_nodes 对已有节点保留状态、更新权重；对新节点创建。"""
    g = SolverGuard(urls=["http://s1:8001"], weights={"http://s1:8001": 1})
    node = g._nodes["http://s1:8001"]
    node.acquire_inflight()
    # 重新配置同 URL 但改权重 → 复用同一对象，inflight 保留
    g.configure_nodes(["http://s1:8001", "http://s2:8001"], weights={"http://s1:8001": 5, "http://s2:8001": 1})
    assert "http://s2:8001" in g._nodes
    assert g._nodes["http://s1:8001"] is node  # 复用
    assert node.weight == 5
    assert node.inflight == 1  # 状态保留


def test_configure_nodes_empty_urls_falls_back_to_config():
    """configure_nodes 收到空列表 → 回退到 config.CF_SOLVER_URL。"""
    g = SolverGuard(urls=["http://s1:8001"])
    g.configure_nodes([], None)
    # 应回退到 config.CF_SOLVER_URL（默认 http://127.0.0.1:8001）
    assert any(n.url == "http://127.0.0.1:8001" for n in g.get_nodes())


def test_acquire_inflight_for_unknown_url_returns_none():
    """acquire_inflight_for 对未知 URL 返回 None。"""
    g = SolverGuard(urls=["http://s1:8001"])
    assert g.acquire_inflight_for("http://unknown:8001") is None


def test_acquire_and_release_inflight_for():
    """acquire/release inflight 计数正确。"""
    g = SolverGuard(urls=["http://s1:8001"])
    node = g.acquire_inflight_for("http://s1:8001")
    assert node is not None
    assert node.inflight == 1
    g.release_inflight_for("http://s1:8001")
    assert node.inflight == 0
    # 释放未知 URL 不报错
    g.release_inflight_for("http://unknown:8001")


def test_select_node_returns_none_when_all_circuit_open():
    """所有节点熔断 → select_node 返回 None。"""
    g = SolverGuard(urls=["http://s1:8001"], circuit_threshold=2)
    g.record_failure("timeout", 1.0, node_url="http://s1:8001")
    g.record_failure("timeout", 1.0, node_url="http://s1:8001")
    # 全熔断；allow_solve 首次 half-open 放行后，select_node 应能选到（half-open）
    # 但把 probe_interval 设很大避免 half-open 干扰
    g2 = SolverGuard(urls=["http://s1:8001"], circuit_threshold=2, probe_interval=9999.0)
    g2.record_failure("timeout", 1.0, node_url="http://s1:8001")
    g2.record_failure("timeout", 1.0, node_url="http://s1:8001")
    # half-open 首次放行后立刻禁用 → select_node 选不到可用节点
    g2.allow_solve()  # 消耗掉首次 half-open 探测
    assert g2.select_node() is None


def test_select_candidates_excludes_urls():
    """select_candidates 排除指定 URL。"""
    g = SolverGuard(urls=["http://s1:8001", "http://s2:8001"])
    cands = g.select_candidates(exclude_urls={"http://s1:8001"})
    assert all(c.url != "http://s1:8001" for c in cands)
    assert any(c.url == "http://s2:8001" for c in cands)


def test_select_candidates_empty_when_all_excluded():
    """全部排除 → 返回空列表。"""
    g = SolverGuard(urls=["http://s1:8001"])
    cands = g.select_candidates(exclude_urls={"http://s1:8001"})
    assert cands == []


def test_circuit_open_cluster_all_open():
    """所有节点熔断时集群 circuit_open=True。"""
    g = SolverGuard(urls=["http://s1:8001", "http://s2:8001"], circuit_threshold=2)
    for url in ("http://s1:8001", "http://s2:8001"):
        g.record_failure("timeout", 1.0, node_url=url)
        g.record_failure("timeout", 1.0, node_url=url)
    assert g.circuit_open is True


def test_circuit_open_empty_nodes_returns_false():
    """无节点时 circuit_open=False。"""
    g = SolverGuard(urls=["http://s1:8001"])
    g._nodes.clear()
    assert g.circuit_open is False
    assert g.consecutive_failures == 0


def test_consecutive_failures_max_across_nodes():
    """consecutive_failures 取所有节点最大值。"""
    g = SolverGuard(urls=["http://s1:8001", "http://s2:8001"])
    g.record_failure("timeout", 1.0, node_url="http://s1:8001")
    g.record_failure("timeout", 1.0, node_url="http://s1:8001")
    g.record_failure("timeout", 1.0, node_url="http://s2:8001")
    assert g.consecutive_failures == 2  # s1 连续 2 次


def test_record_success_without_node_url_single_node():
    """不指定 node_url 且只有 1 个节点 → 同步更新该节点。"""
    g = SolverGuard(urls=["http://s1:8001"], circuit_threshold=3)
    g.record_failure("timeout", 1.0)  # 单节点
    g.record_failure("timeout", 1.0)
    g.record_success(0.5)  # 不指定 node_url
    node = list(g._nodes.values())[0]
    assert node.consecutive_failures == 0
    assert node._success == 1


def test_record_failure_without_node_url_single_node():
    """不指定 node_url 且只有 1 个节点 → 失败累计到该节点。"""
    g = SolverGuard(urls=["http://s1:8001"], circuit_threshold=5)
    g.record_failure("timeout", 1.0)
    node = list(g._nodes.values())[0]
    assert node.consecutive_failures == 1
    assert node._failure == 1


def test_snapshot_cluster_status_degraded():
    """部分节点熔断 → cluster_status=degraded。"""
    g = SolverGuard(urls=["http://s1:8001", "http://s2:8001"], circuit_threshold=2)
    g.record_failure("timeout", 1.0, node_url="http://s1:8001")
    g.record_failure("timeout", 1.0, node_url="http://s1:8001")
    s = g.snapshot()
    assert s["solver_status"] == "degraded"
    assert s["healthy_node_count"] == 1
    assert s["node_count"] == 2


def test_record_rejected_increments_total():
    """record_rejected 累计全局拒绝数。"""
    g = SolverGuard()
    assert g.snapshot()["rejected_total"] == 0
    g.record_rejected()
    g.record_rejected()
    assert g.snapshot()["rejected_total"] == 2


def test_get_nodes_returns_list():
    """get_nodes 返回节点列表。"""
    g = SolverGuard(urls=["http://s1:8001", "http://s2:8001"])
    nodes = g.get_nodes()
    assert len(nodes) == 2
    assert all(isinstance(n, SolverNodeState) for n in nodes)


def test_node_is_rate_limited_reflects_cooldown():
    """is_rate_limited 在 429 冷却期内返回 True，过期返回 False。"""
    g = SolverGuard(urls=["http://s1:8001"], rate_limit_cooldown=0.1)
    node = list(g._nodes.values())[0]
    assert node.is_rate_limited() is False
    g.record_failure("rate_limit", 0.5, node_url="http://s1:8001")
    assert node.is_rate_limited() is True
    time.sleep(0.11)
    assert node.is_rate_limited() is False
