"""号池补满速率监控（P3-4）集成测试：/v1/account-pool 返回 growth 画像。"""
import pytest


@pytest.mark.integration
async def test_account_pool_growth_field(app_with_mocks):
    """/v1/account-pool 顶层含 growth 字段且结构完整（号池补满速率监控）。"""
    r = await app_with_mocks.get("/v1/account-pool")
    assert r.status_code == 200
    body = r.json()
    # v6.6.0: growth 画像必须存在（前端字段名 growth_stats，见 Accounts.tsx/api.ts）
    assert "growth_stats" in body, "account-pool 缺少 growth_stats 字段"
    g = body["growth_stats"]
    for key in ("total", "new_in_24h", "new_in_7d", "avg_daily_7d",
                "ok", "target", "gap", "eta_days"):
        assert key in g, f"growth 缺字段 {key}"
    # 结构与数值类型
    assert isinstance(g["total"], int)
    assert isinstance(g["new_in_24h"], int)
    assert isinstance(g["target"], int)
    assert g["gap"] == max(0, g["target"] - g["ok"])
    # 速率为 0 时 eta_days 为 None（前端显示「—」），有速率时为 float
    if g["new_in_24h"] > 0:
        assert g["eta_days"] is None or isinstance(g["eta_days"], float)
