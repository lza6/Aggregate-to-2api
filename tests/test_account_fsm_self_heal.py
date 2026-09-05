"""P1-7 号池 FSM 自愈：cooling→active 自愈路径加「可配重试次数 + 指数退避」。

契约：
- 无 registerer 时 wake_cooling_accounts 保持原「到期直接唤醒」行为（向后兼容）。
- 有 registerer 时走自愈：签到成功→active（retry 清零）；失败→retry+1 + 指数退避，
  超 IF_ACCOUNT_SELFHEAL_MAX_RETRY 才转 dead。
- 重试计数为内存态（self._selfheal_retry），不改 DB schema。
"""

import os
import time

import pytest

os.environ.setdefault("IF_ACCOUNT_AUTO", "0")


class _FakeReg:
    """假注册器：checkin 返回 int/dict=成功，None=失败（cookie 失效）。

    注意 _result 必须显式区分"未设"(用哨兵)与 None(失败)：原 `result if result is not None else 8`
    会让 `result=None` 也落到默认 8（成功），无法表达失败用例。用 _SENTINEL 解决。
    """

    _SENTINEL = object()

    def __init__(self, result=_SENTINEL):
        self._result = 8 if result is self._SENTINEL else result
        self.checkin_calls = 0

    async def checkin(self, acc):
        self.checkin_calls += 1
        return self._result


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


async def _set_cooling_since(pool, email, ts):
    conn = await pool._ensure_conn()
    async with pool._lock:
        await conn.execute("UPDATE accounts SET cooling_since=? WHERE email=?", (ts, email))
        await conn.commit()


@pytest.mark.asyncio
async def test_self_heal_success_to_active(pool):
    """签到成功 → active，retry 清零，credits 更新。"""
    await pool.add("nanobanana", "sh1@t.com", "c", credits=0, status="cooling")
    await _set_cooling_since(pool, "sh1@t.com", time.time() - 999999)
    pool.registerers["nanobanana"] = _FakeReg(result=10)
    woken = await pool.wake_cooling_accounts("nanobanana", cooling_timeout=72000)
    assert woken == 1
    active = await pool.get("nanobanana")
    assert len(active) == 1
    assert active[0]["email"] == "sh1@t.com"
    assert active[0]["credits"] == 10
    assert ("nanobanana", "sh1@t.com") not in pool._selfheal_retry


@pytest.mark.asyncio
async def test_self_heal_fail_backoff(pool):
    """签到失败 1 次 → 仍 cooling，退避时间递增（未达 max_retry）。"""
    await pool.add("nanobanana", "sh2@t.com", "c", credits=0, status="cooling")
    await _set_cooling_since(pool, "sh2@t.com", time.time() - 999999)
    pool.registerers["nanobanana"] = _FakeReg(result=None)
    # 未达 max_retry（默认 3）→ 不转 active，返回 woken=0（仍 cooling）
    woken = await pool.wake_cooling_accounts("nanobanana", cooling_timeout=72000)
    assert woken == 0
    cooling = await pool.list("nanobanana", status="cooling")
    assert len(cooling) == 1
    assert cooling[0]["email"] == "sh2@t.com"
    assert pool._selfheal_retry[("nanobanana", "sh2@t.com")] == 1


@pytest.mark.asyncio
async def test_self_heal_max_retry_to_dead(pool, monkeypatch):
    """连续失败超 IF_ACCOUNT_SELFHEAL_MAX_RETRY → 转 dead。"""
    monkeypatch.setattr("api.account_pool.SELFHEAL_MAX_RETRY", 2)
    await pool.add("nanobanana", "sh3@t.com", "c", credits=0, status="cooling")
    reg = _FakeReg(result=None)
    pool.registerers["nanobanana"] = reg
    # 第 1 次失败 → retry=1，仍 cooling
    await pool.wake_cooling_accounts("nanobanana", cooling_timeout=0)
    assert pool._selfheal_retry[("nanobanana", "sh3@t.com")] == 1
    # 第 2 次失败 → retry=2 >= max → dead
    await pool.wake_cooling_accounts("nanobanana", cooling_timeout=0)
    dead = await pool.list("nanobanana", status="dead")
    assert len(dead) == 1
    assert dead[0]["email"] == "sh3@t.com"
    assert ("nanobanana", "sh3@t.com") not in pool._selfheal_retry


@pytest.mark.asyncio
async def test_self_heal_reset_on_new_cooling(pool, monkeypatch):
    """mark_cooling 重置 retry（新一轮冷却从头计）。"""
    monkeypatch.setattr("api.account_pool.SELFHEAL_MAX_RETRY", 3)
    await pool.add("nanobanana", "sh4@t.com", "c", credits=0, status="cooling")
    pool._selfheal_retry[("nanobanana", "sh4@t.com")] = 2
    await pool.mark_cooling("nanobanana", "sh4@t.com")
    assert ("nanobanana", "sh4@t.com") not in pool._selfheal_retry


@pytest.mark.asyncio
async def test_wake_no_registerer_legacy(pool):
    """无 registerer → 保持原到期直接唤醒行为（向后兼容）。"""
    await pool.add("nanobanana", "sh5@t.com", "c", credits=0, status="cooling")
    await _set_cooling_since(pool, "sh5@t.com", time.time() - 999999)
    woken = await pool.wake_cooling_accounts("nanobanana", cooling_timeout=72000)
    assert woken == 1
    assert len(await pool.get("nanobanana")) == 1
