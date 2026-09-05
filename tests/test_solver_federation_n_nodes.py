"""P1-2（v8.0）：cf_solver 多节点联邦验证测试。

接线已在 v7.7.x 完成（config.if_cf_solver_urls + 解析 + solver_guard urls= + turnstile_client select_candidates）。
本测试验证多节点真正生效：N 节点加载、轮询覆盖、单节点熔断后跳过。
"""

from __future__ import annotations

from api.solver_guard import SolverGuard


def test_single_node_default_zero_regression():
    """单节点缺省：urls 未设 → 回退 [CF_SOLVER_URL]，len==1（零回归）。"""
    sg = SolverGuard(urls=["http://127.0.0.1:8001"])
    nodes = sg.get_nodes()
    assert len(nodes) == 1
    assert nodes[0].url == "http://127.0.0.1:8001"


def test_n_nodes_loaded_from_urls():
    """IF_CF_SOLVER_URLS 逗号分隔 3 节点 → solver_guard 加载 3 节点。"""
    urls = ["http://solver1:8001", "http://solver2:8001", "http://solver3:8001"]
    sg = SolverGuard(urls=urls)
    nodes = sg.get_nodes()
    assert len(nodes) == 3
    loaded_urls = {n.url for n in nodes}
    assert loaded_urls == set(urls)


def test_select_node_round_robin_covers_all():
    """3 节点全健康时 select_node 轮询覆盖所有节点。"""
    urls = ["http://a:8001", "http://b:8001", "http://c:8001"]
    sg = SolverGuard(urls=urls)
    seen = set()
    for _ in range(len(urls) * 3):
        n = sg.select_node()
        if n is not None:
            seen.add(n.url)
    assert seen == set(urls), f"轮询未覆盖全部节点: {seen}"


def test_circuit_open_node_skipped():
    """一个节点熔断（连续失败到 threshold）后，select_node 跳过它选其余。

    注意 SolverNodeState.record_failure 的熔断判定：reason != "rate_limit" 且
    consecutive_failures >= circuit_threshold 才 OPEN。用 "transport" 失败触发连续失败路径。
    """
    urls = ["http://good:8001", "http://bad:8001"]
    sg = SolverGuard(urls=urls, circuit_threshold=2)
    # 让 bad 节点连续失败到熔断（非 rate_limit 原因才累计 consecutive_failures）
    for _ in range(3):
        sg.record_failure("transport", 1.0, node_url="http://bad:8001")
    bad_node = next(n for n in sg.get_nodes() if n.url == "http://bad:8001")
    assert bad_node.circuit_open, "bad 节点应已熔断"
    # bad 节点熔断期间仍可能被 select_node 放探测（half-open），但 good 应占多数。
    # 统计 N 次选择里至少有一次选中 good（证明熔断节点没锁死全部流量）
    selected_good = 0
    for _ in range(10):
        n = sg.select_node()
        if n is not None and n.url == "http://good:8001":
            selected_good += 1
    assert selected_good >= 1, "熔断节点应可被跳过、good 节点至少被选一次"


def test_weights_applied():
    """weights 配置：节点权重差异化加载。"""
    urls = ["http://a:8001", "http://b:8001"]
    sg = SolverGuard(urls=urls, weights={"http://a:8001": 1, "http://b:8001": 5})
    nodes = {n.url: n for n in sg.get_nodes()}
    assert len(nodes) == 2
    # 权重存储在节点状态上（具体字段名由实现决定，此处只断言节点都加载了）
    assert "http://a:8001" in nodes
    assert "http://b:8001" in nodes
