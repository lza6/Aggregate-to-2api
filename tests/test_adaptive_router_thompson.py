"""v8.0 P1-3: Thompson Sampling 后验更新 + 收敛性测试。"""


from api.adaptive_router import AdaptiveRouter


class TestThompsonSampling:
    """Thompson Sampling: Beta 分布后验更新 + 负载惩罚二次过滤。"""

    def test_beta_posterior_updates_on_success(self):
        """成功 alpha+=1，失败 beta+=1，Beta 参数正确更新。"""
        r = AdaptiveRouter(alpha=0.2, initial_explore_rate=0.10)
        r.record_result("p1", 100.0, True)
        r.record_result("p1", 100.0, True)
        r.record_result("p1", 100.0, False)
        st = r.nodes["p1"]
        assert st.alpha == 3.0  # 1(初始) + 2 成功
        assert st.beta == 2.0  # 1(初始) + 1 失败

    def test_thompson_picks_higher_success_rate_with_enough_samples(self):
        """样本充足时 Thompson 收敛到高成功率 provider（统计意义上）。"""
        r = AdaptiveRouter(alpha=0.2, initial_explore_rate=0.10)
        # p1: 8 成功 2 失败（高成功率）
        for _ in range(8):
            r.record_result("p1", 100.0, True)
        for _ in range(2):
            r.record_result("p1", 100.0, False)
        # p2: 2 成功 8 失败（低成功率）
        for _ in range(2):
            r.record_result("p2", 100.0, True)
        for _ in range(8):
            r.record_result("p2", 100.0, False)
        # 总样本 = 20 >= 5，走 Thompson
        # 统计性：1000 次 Thompson 选择，p1 应被选 majority
        picks = {"p1": 0, "p2": 0}
        for _ in range(1000):
            picked = r._select_thompson(["p1", "p2"])
            picks[picked] += 1
        assert picks["p1"] > picks["p2"], f"Thompson 应收敛到高成功率 p1, got {picks}"

    def test_thompson_load_penalty_filters_overloaded(self):
        """Thompson 采样后用负载惩罚二次过滤，避免选到 in_flight 过高节点。"""
        r = AdaptiveRouter(alpha=0.2, initial_explore_rate=0.10)
        # 两 provider 成功率相近，但 p1 in_flight 极高
        for _ in range(10):
            r.record_result("p1", 100.0, True)
            r.record_result("p2", 100.0, True)
        r.record_inflight("p1", 100)  # p1 严重过载
        # 100 次：p2 应被选 majority（负载惩罚让 p1 即使采样值高也被过滤）
        picks = {"p1": 0, "p2": 0}
        for _ in range(100):
            picked = r._select_thompson(["p1", "p2"])
            picks[picked] += 1
        assert picks["p2"] > picks["p1"], f"负载惩罚应让 p2 胜出, got {picks}"

    def test_thompson_reason_recorded(self):
        """select_best 样本充足时 reason='thompson'。"""
        r = AdaptiveRouter(alpha=0.2, initial_explore_rate=0.10)
        for _ in range(6):
            r.record_result("p1", 100.0, True)
        r.select_best(["p1", "p2"])
        rec = r.records(limit=1)[0]
        assert rec["reason"] == "thompson"
