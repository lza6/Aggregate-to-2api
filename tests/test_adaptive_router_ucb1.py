"""v8.0 P1-3: UCB1 冷启动强探索 + 样本充足切换测试。"""


from api.adaptive_router import AdaptiveRouter


class TestUCB1ColdStart:
    """UCB1: 冷启动强探索 + 样本充足切 Thompson。"""

    def test_ucb1_cold_start_explores_all(self):
        """全冷启动（total_pulls=0）UCB1 随机选，覆盖所有候选。"""
        r = AdaptiveRouter(alpha=0.2, initial_explore_rate=0.10)
        picks = {"p1": 0, "p2": 0, "p3": 0}
        for _ in range(100):
            picked = r._select_ucb1(["p1", "p2", "p3"])
            picks[picked] += 1
        # 冷启动随机应覆盖所有候选（每个至少被选 1 次）
        assert all(v > 0 for v in picks.values()), f"UCB1 冷启动应探索全部, got {picks}"

    def test_ucb1_favors_unsampled(self):
        """UCB1 对未采样（pulls 少）的 provider 给高置信上界，强制探索。"""
        r = AdaptiveRouter(alpha=0.2, initial_explore_rate=0.10)
        # p1 被选 5 次都成功，p2 从未被选
        for _ in range(5):
            r._record_inflight_locked("p1")
            r.record_result("p1", 100.0, True)
        # UCB1: p2 的 n_i=1(初始setdefault), p1 的 n_i=5
        # p2 置信上界更大 → 应被选（强探索）
        picks = {"p1": 0, "p2": 0}
        for _ in range(50):
            picked = r._select_ucb1(["p1", "p2"])
            picks[picked] += 1
        assert picks["p2"] > 0, "UCB1 应探索未采样的 p2"

    def test_select_best_uses_ucb1_on_cold_start(self):
        """select_best 冷启动（样本 < 5）reason='ucb1_explore'。"""
        r = AdaptiveRouter(alpha=0.2, initial_explore_rate=0.10)
        r.select_best(["p1", "p2"])
        rec = r.records(limit=1)[0]
        assert rec["reason"] == "ucb1_explore"

    def test_select_best_switches_to_thompson_after_warmup(self):
        """样本 >= 5 后 select_best 切 Thompson。"""
        r = AdaptiveRouter(alpha=0.2, initial_explore_rate=0.10)
        for _ in range(6):
            r.record_result("p1", 100.0, True)
        r.select_best(["p1", "p2"])
        rec = r.records(limit=1)[0]
        assert rec["reason"] == "thompson"

    def test_explore_false_overrides_algorithm(self):
        """explore=False 强制 best_score，不走 UCB1/Thompson。"""
        r = AdaptiveRouter(alpha=0.2, initial_explore_rate=0.10)
        r.select_best(["p1", "p2"], explore=False)
        rec = r.records(limit=1)[0]
        assert rec["reason"] == "best_score"
