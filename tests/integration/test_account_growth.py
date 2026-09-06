"""号池补满速率监控（P3-4）集成测试：/v1/account-pool 返回 growth 画像。"""

import asyncio

import pytest


@pytest.mark.integration
async def test_account_pool_growth_field(app_with_mocks):
    """/v1/account-pool 顶层含 growth 字段且结构完整（号池补满速率监控）。

    P2-F1 根治 CI 1/37 404 时序：app_with_mocks fixture 的 healthz 就绪等待
    不保证 account_pool DB 已建表/就绪。此处加最终一致性轮询，等端点
    返回 200 再断言（timeout 8s），消除时序竞争。
    """
    r = None
    for _ in range(40):
        r = await app_with_mocks.get("/v1/account-pool")
        if r.status_code == 200:
            break
        await asyncio.sleep(0.2)
    assert r is not None and r.status_code == 200, f"account-pool 未就绪: {r.status_code if r else 'None'}"
    body = r.json()
    # v6.6.0: growth 画像必须存在（前端字段名 growth_stats，见 Accounts.tsx/api.ts）
    assert "growth_stats" in body, "account-pool 缺少 growth_stats 字段"
    g = body["growth_stats"]
    for key in ("total", "new_in_24h", "new_in_7d", "avg_daily_7d", "ok", "target", "gap", "eta_days"):
        assert key in g, f"growth 缺字段 {key}"
    # 结构与数值类型
    assert isinstance(g["total"], int)
    assert isinstance(g["new_in_24h"], int)
    assert isinstance(g["target"], int)
    assert g["gap"] == max(0, g["target"] - g["ok"])
    # 速率为 0 时 eta_days 为 None（前端显示「—」），有速率时为 float
    if g["new_in_24h"] > 0:
        assert g["eta_days"] is None or isinstance(g["eta_days"], float)
