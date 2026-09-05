"""P1-7 余额预测：基于近 7 天消耗速率 + 当前余额，预测号池耗尽时间。

predict_exhaustion(provider) -> {
    "hours_to_exhaustion": float | None,   # None = 无消耗数据/零速率
    "burn_rate_per_day": float,            # 日均积分消耗速率
    "current_credits": int,                # 当前可用余额（ok/active/working）
}

口径说明（近似）：credits_used_total 为账号累计消耗（无历史明细），
以近 7 天有使用记录的账号累计消耗 / 实际使用跨度天数 估算速率——
跨度取 [min(last_used_at), max(last_used_at)]，下限 1 小时防除零。
"""

import os
import time

import pytest

os.environ.setdefault("IF_ACCOUNT_AUTO", "0")


@pytest.fixture
def pool(tmp_path):
    from api.account_pool import AccountPool

    p = AccountPool(str(tmp_path / "acc.db"))
    yield p
    try:
        conn = getattr(p, "_conn", None)
        if conn is not None:
            raw = getattr(conn, "_connection", None)
            if raw is not None:
                raw.close()
            stop = getattr(conn, "_stop_running", None)
            if stop is not None:
                stop()
    except Exception:
        pass


async def _seed_usage(pool, email, credits, used_total, last_used_at):
    """直插 SQL 设置消耗画像（绕开 consume_credits 的实时时间戳）。"""
    conn = await pool._ensure_conn()
    async with pool._lock:
        await conn.execute(
            "UPDATE accounts SET credits=?, credits_used_total=?, last_used_at=?, updated_at=? "
            "WHERE provider='nanobanana' AND email=?",
            (credits, used_total, last_used_at, time.time(), email),
        )
        await conn.commit()


@pytest.mark.asyncio
async def test_predict_positive_hours(pool):
    """有消耗速率 + 有限余额 → 预测出正数 hours。"""
    now = time.time()
    await pool.add("nanobanana", "p1@t.com", "c", credits=60, status="active")
    await pool.add("nanobanana", "p2@t.com", "c", credits=40, status="active")
    # p1 两天前用了 50 分，p2 刚用 50 分 → span≈2d, used=100 → burn≈50/d → 100 余额 ≈ 48h
    await _seed_usage(pool, "p1@t.com", 60, 50, now - 2 * 86400)
    await _seed_usage(pool, "p2@t.com", 40, 50, now - 60)
    r = await pool.predict_exhaustion("nanobanana")
    assert r["current_credits"] == 100
    assert r["burn_rate_per_day"] > 0
    assert r["hours_to_exhaustion"] is not None
    assert 12 < r["hours_to_exhaustion"] < 96  # 量级合理（≈48h）


@pytest.mark.asyncio
async def test_predict_zero_burn_returns_none(pool):
    """零消耗速率（无使用记录）→ hours=None。"""
    await pool.add("nanobanana", "p3@t.com", "c", credits=100, status="active")
    r = await pool.predict_exhaustion("nanobanana")
    assert r["hours_to_exhaustion"] is None
    assert r["burn_rate_per_day"] == 0.0
    assert r["current_credits"] == 100


@pytest.mark.asyncio
async def test_predict_rich_pool_large_hours(pool):
    """余额充足（速率极低）→ hours 很大。"""
    now = time.time()
    await pool.add("nanobanana", "p4@t.com", "c", credits=10000, status="active")
    # 2 天前只用了 1 分 → burn≈0.5/d → 10000 分 ≈ 20000d，远超一周
    await _seed_usage(pool, "p4@t.com", 10000, 1, now - 2 * 86400)
    r = await pool.predict_exhaustion("nanobanana")
    assert r["hours_to_exhaustion"] is not None
    assert r["hours_to_exhaustion"] > 24 * 7


@pytest.mark.asyncio
async def test_predict_empty_pool(pool):
    """空号池 → hours=None，credits=0。"""
    r = await pool.predict_exhaustion("nanobanana")
    assert r["hours_to_exhaustion"] is None
    assert r["current_credits"] == 0
