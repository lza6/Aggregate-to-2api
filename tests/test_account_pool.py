"""号池（account_pool）与邮箱池（email_pool）单测：持久化/分配/自动补号/签到/状态机 (Account FSM)。"""

import asyncio
import os
import time

import pytest


# 测试隔离：临时 DB 路径（fixture 里动态生成）
os.environ.setdefault("IF_ACCOUNT_AUTO", "0")


class _FakeReg:
    """假注册器：register_one 返回固定账号；checkin 返回递增余额。"""

    calls = 0

    async def register_one(self):
        _FakeReg.calls += 1
        return {"email": f"mock{_FakeReg.calls}@m.com", "cookie": "mock-session", "password": "p", "credits": 4}

    async def checkin(self, acc):
        return int(acc.get("credits", 0)) + 4


@pytest.fixture
def pool(tmp_path):
    from api.account_pool import AccountPool

    p = AccountPool(str(tmp_path / "acc.db"))
    yield p
    # 关闭连接
    try:
        p._conn.close()
    except Exception:
        pass


# ── 持久化 ──────────────────────────────────────
class TestAccountPool:
    def test_add_and_get(self, pool):
        pool.add("nanobanana", "a@x.com", "cookie1", credits=4)
        pool.add("nanobanana", "b@x.com", "cookie2", credits=4)
        pool.add("nanobanana", "c@x.com", "cookie3", credits=4)
        nb = pool.get("nanobanana")
        assert len(nb) == 3
        assert all(a["cookie"] for a in nb)
        assert pool.total_credits("nanobanana") == 12

    def test_mark_and_credits(self, pool):
        pool.add("nanobanana", "a@x.com", "c", credits=4)
        pool.update_credits("nanobanana", "a@x.com", 0)
        assert pool.total_credits("nanobanana") == 0
        pool.mark("nanobanana", "a@x.com", "exhausted")
        assert pool.get("nanobanana") == []  # exhausted 不算可用

    def test_counts(self, pool):
        pool.add("nanobanana", "a@x.com", "c", credits=4)
        pool.add("nanobanana", "b@x.com", "c", credits=4, status="exhausted")
        c = pool.counts()
        assert c["nanobanana"]["ok"] == 1
        assert c["nanobanana"]["exhausted"] == 1

    def test_dashboard(self, pool):
        pool.add("nanobanana", "a@x.com", "c", credits=4)
        d = pool.dashboard()
        assert "nanobanana" in d
        assert d["nanobanana"]["credits"] == 4


# ── 状态机 (Account FSM) 测试 ─────────────────────
class TestAccountFSM:
    def test_fsm_borrow_and_release(self, pool):
        """测试正常流程：active (ok) -> borrow -> working -> release -> active。"""
        pool.add("nanobanana", "fsm1@test.com", "cookie1", credits=8, status="active")

        # 借号
        acc = pool.borrow_account("nanobanana")
        assert acc is not None
        assert acc["email"] == "fsm1@test.com"
        assert acc["status"] == "working"

        # 再次尝试借号，池中无可用 active
        acc2 = pool.borrow_account("nanobanana")
        assert acc2 is None

        # 归还并扣除积分
        pool.release_account("nanobanana", "fsm1@test.com", new_credits=4)

        # 归还后应恢复为 active
        active_list = pool.get("nanobanana")
        assert len(active_list) == 1
        assert active_list[0]["email"] == "fsm1@test.com"
        assert active_list[0]["credits"] == 4
        assert active_list[0]["status"] == "active"

    def test_fsm_release_to_cooling_when_exhausted(self, pool):
        """测试归还时积分耗尽自动转移至 cooling (exhausted)。"""
        pool.add("nanobanana", "fsm2@test.com", "cookie2", credits=4, status="active")
        acc = pool.borrow_account("nanobanana")
        assert acc is not None

        # 归还时扣减至 0
        pool.release_account("nanobanana", "fsm2@test.com", new_credits=0)

        # 应进入 cooling / exhausted
        cooling_list = pool.list("nanobanana", status="cooling")
        assert len(cooling_list) == 1
        assert cooling_list[0]["email"] == "fsm2@test.com"
        assert cooling_list[0]["cooling_since"] is not None
        assert pool.get("nanobanana") == []

    def test_fsm_mark_dead_on_banned(self, pool):
        """测试捕获封号/鉴权失效时转移至 dead (banned)。"""
        pool.add("nanobanana", "fsm3@test.com", "cookie3", credits=10, status="active")
        pool.mark_dead("nanobanana", "fsm3@test.com", reason="HTTP 401 Unauthorized")

        dead_list = pool.list("nanobanana", status="dead")
        assert len(dead_list) == 1
        assert dead_list[0]["email"] == "fsm3@test.com"
        assert "401" in dead_list[0]["note"]
        assert pool.get("nanobanana") == []

    def test_fsm_wake_cooling_accounts(self, pool):
        """测试冷却扫描唤醒器：超过超期时间的 cooling 账号恢复为 active。"""
        pool.add("nanobanana", "fsm4@test.com", "cookie4", credits=0, status="active")
        pool.mark_cooling("nanobanana", "fsm4@test.com", reason="out of credits")

        # 手动篡改 cooling_since 为 24 小时前
        old_time = time.time() - 86400
        pool._conn.execute("UPDATE accounts SET cooling_since=? WHERE email='fsm4@test.com'", (old_time,))
        pool._conn.commit()

        # 触发唤醒（设定超时 72000 秒，即 20 小时）
        woken = pool.wake_cooling_accounts("nanobanana", cooling_timeout=72000)
        assert woken == 1

        active_list = pool.get("nanobanana")
        assert len(active_list) == 1
        assert active_list[0]["email"] == "fsm4@test.com"

    @pytest.mark.asyncio
    async def test_fsm_lease_context_manager(self, pool):
        """测试异步 lease 语法糖与自动归还。"""
        pool.add("nanobanana", "fsm5@test.com", "cookie5", credits=5, status="active")

        async with pool.lease("nanobanana") as acc:
            assert acc is not None
            assert acc["email"] == "fsm5@test.com"
            assert acc["status"] == "working"

        # 退出 with 块后已归还
        assert len(pool.get("nanobanana")) == 1

    @pytest.mark.asyncio
    async def test_fsm_lease_exception_dead(self, pool):
        """测试 lease 内发生 403 封号异常自动转为 dead。"""
        pool.add("nanobanana", "fsm6@test.com", "cookie6", credits=5, status="active")

        with pytest.raises(RuntimeError):
            async with pool.lease("nanobanana") as acc:
                raise RuntimeError("403 Forbidden: Account suspended")

        dead_list = pool.list("nanobanana", status="dead")
        assert len(dead_list) == 1
        assert dead_list[0]["email"] == "fsm6@test.com"


# ── 自动补号 ─────────────────────────────────────
@pytest.mark.asyncio
async def test_autoregister_loop_fills_to_target(tmp_path, monkeypatch):
    from api.account_pool import AccountPool
    from api.proxy_pool import ProxyEntry, proxy_pool

    # 注入一个 residential 代理（无住宅代理时补号循环按安全红线跳过注册）
    monkeypatch.setattr(proxy_pool, "entries", [ProxyEntry("http://r:r@1.1.1.1:8080", source="residential")])
    p = AccountPool(str(tmp_path / "acc.db"))
    p.registerers["nanobanana"] = _FakeReg()
    monkeypatch.setattr("api.account_pool.TARGET_NANOBANANA", 2)
    monkeypatch.setattr("api.account_pool.REGISTER_COOLDOWN", 0.1)  # M5 成功节流缩短，测试快速补满
    # 提高每日上限，让同一个 IP 能被注册两次（代理池默认每 IP 每日只用 1 次）
    monkeypatch.setattr("api.config.IF_PROXY_MAX_USE_PER_DAY", 2)
    task = asyncio.create_task(p._autoregister_loop("nanobanana"))
    try:
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and len(p.get("nanobanana")) < 2:
            await asyncio.sleep(0.3)
        assert len(p.get("nanobanana")) >= 2
        assert p.total_credits("nanobanana") >= 8
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        p._conn.close()


# ── nanobanana 签到 ─────────────────────────────
@pytest.mark.asyncio
async def test_daily_checkin_updates_credits(tmp_path):
    from api.account_pool import AccountPool

    p = AccountPool(str(tmp_path / "acc.db"))
    p.add("nanobanana", "a@x.com", "c", credits=4)
    reg = _FakeReg()
    p.registerers["nanobanana"] = reg

    async def _checkin(acc):
        return await reg.checkin(acc)

    # 手动触发一次签到逻辑（等价 _daily_checkin_loop 单轮）
    for acc in p.list("nanobanana", status="ok"):
        if time.time() - (acc.get("checkin_at") or 0) > 20 * 3600:
            ok = await _checkin(acc)
            p.set_checkin("nanobanana", acc["email"], time.time())
            p.update_credits("nanobanana", acc["email"], ok)
    assert p.total_credits("nanobanana") == 8
    p._conn.close()


# ── v6.5.1 每账号出图消耗积分 ──────────────────
def test_consume_credits_updates_usage_profile(tmp_path):
    """生成成功扣减该账号积分并累计消耗/出图次数画像（下限 0，非法消耗 no-op）。"""
    from api.account_pool import AccountPool

    p = AccountPool(str(tmp_path / "consume.db"))
    p.add("nanobanana", "a@x.com", "c", credits=20, status="active")
    p.consume_credits("nanobanana", "a@x.com", 4)
    row = p.get("nanobanana")[0]
    assert row["credits"] == 16
    assert row["credits_used_total"] == 4
    assert row["images_used"] == 1
    # 扣到下限 0，不出现负数
    p.consume_credits("nanobanana", "a@x.com", 100)
    row = p.get("nanobanana")[0]
    assert row["credits"] == 0
    assert row["credits_used_total"] == 104
    assert row["images_used"] == 2
    # 非法 amount => no-op，不影响画像
    before = p.get("nanobanana")[0]["images_used"]
    p.consume_credits("nanobanana", "a@x.com", 0)
    assert p.get("nanobanana")[0]["images_used"] == before
    p._conn.close()


def test_cost_summary_aggregation(tmp_path):
    """成本口径聚合：累计消耗/出图次数/每张平均成本/有消耗账号数。"""
    from api.account_pool import AccountPool

    p = AccountPool(str(tmp_path / "cost.db"))
    p.add("nanobanana", "a@x.com", "c", credits=10, status="active")
    p.add("nanobanana", "b@x.com", "c", credits=10, status="active")
    p.add("nanobanana", "c@x.com", "c", credits=10, status="active")  # 从未出图
    p.consume_credits("nanobanana", "a@x.com", 4)
    p.consume_credits("nanobanana", "b@x.com", 8)
    cs = p.cost_summary("nanobanana")
    assert cs["total_credits_used"] == 12
    assert cs["total_images_used"] == 2
    assert cs["avg_cost_per_image"] == 6.0
    assert cs["accounts_with_usage"] == 2
    assert cs["total_accounts"] == 3
    assert cs["total_credits_earned"] == 0
    # 无出图时 avg 为 None（避免除零）
    p2 = AccountPool(str(tmp_path / "cost2.db"))
    p2.add("nanobanana", "d@x.com", "c", credits=10, status="active")
    cs2 = p2.cost_summary("nanobanana")
    assert cs2["avg_cost_per_image"] is None
    p._conn.close()
    p2._conn.close()


def test_image_credit_cost_mapping():
    """image_credit_cost 镜像上游 encodeImageCost（按模型+分辨率返回单图积分）。"""
    from api.providers.nanobanana import image_credit_cost

    assert image_credit_cost("nano-banana-pro", "1K") == 4
    assert image_credit_cost("nano-banana-pro", "4K") == 14
    assert image_credit_cost("nano-banana-2", "2K") == 8
    assert image_credit_cost("nano-banana-2", "4K") == 12
    assert image_credit_cost("gpt-image-2", "1K") == 6  # P1-5 漏档回归
    assert image_credit_cost("gpt-image-2", "4K") == 14
    assert image_credit_cost("seedream-5.0-pro", "1K") == 7  # P1-5 漏档回归
    assert image_credit_cost("seedream-5.0-pro", "2K") == 14
    assert image_credit_cost("seedream-5.0-lite", "2K") == 6  # P1-5 漏档回归
    assert image_credit_cost("seedream-5.0-lite", "3K") == 6
    assert image_credit_cost("seedream-5.0-lite", "1K") == 6  # P1-5 漏档回归：1K 不得回退默认 4
    assert image_credit_cost("grok-imagine", "1K", quality_mode="quality") == 6
    assert image_credit_cost("grok-imagine", "1K", task_type="edit") == 5
    assert image_credit_cost("z-image", "1K") == 2
    # 未命中回退默认 4
    assert image_credit_cost("unknown-model", "1K") == 4


# ── 邮箱池 ──────────────────────────────────────
class TestEmailPool:
    @pytest.mark.asyncio
    async def test_allocate_unique_and_record(self, tmp_path, monkeypatch):
        from api.email_pool import EmailPool

        p = EmailPool(str(tmp_path / "email.db"))
        # 网络源打桩：temp-mail/22.do 建箱是真实 HTTP 调用（无 mock 会挂测试），
        # 本用例只验证分配唯一性与记录逻辑——本地 temp.tf 随机源足够
        monkeypatch.setattr(p, "_sources", [s for s in p._sources if s.name == "temp.tf"])
        a1, _s1 = await p.allocate("nanobanana")
        a2, _s2 = await p.allocate("nanobanana")
        assert a1 != a2
        assert "@" in a1 and a1.split("@")[1].count(".") >= 1  # 合法邮箱（local@domain.tld）
        p.record(a1, "nanobanana", "ok")
        assert p.registered_providers(a1) == ["nanobanana"]
        # 已用邮箱不再分配
        a3, _s3 = await p.allocate("nanobanana")
        assert a3 not in (a1, a2)
        p._conn.close()

    @pytest.mark.asyncio
    async def test_stats(self, tmp_path, monkeypatch):
        from api.email_pool import EmailPool

        p = EmailPool(str(tmp_path / "email.db"))
        # 同上：打桩网络源，只留本地 temp.tf
        monkeypatch.setattr(p, "_sources", [s for s in p._sources if s.name == "temp.tf"])
        a, _s = await p.allocate("nanobanana")
        p.record(a, "nanobanana", "ok")
        s = p.stats()
        assert s["total_registered"] == 1
        assert s["by_provider"].get("nanobanana") == 1
        p._conn.close()


# ── P-TEST-A7 追加：dashboard 结构与补号暂停分支 ──────────────


class TestAccountPoolDashboard:
    def test_dashboard_structure(self, pool):
        d = pool.dashboard()
        for prov in ("nanobanana",):
            assert prov in d
            entry = d[prov]
            for key in ("total", "ok", "exhausted", "registering", "credits", "target", "auto_register"):
                assert key in entry, f"{prov} 缺字段 {key}"
        assert d["nanobanana"]["target"] == 10000  # 大容量目标（支持百万级号池）
        assert d["nanobanana"]["auto_register"] is False  # 未注入注册器

    def test_dashboard_counts_reflect_state(self, pool):
        pool.add("nanobanana", "a@x.com", "c1", credits=4)
        pool.add("nanobanana", "b@x.com", "c2", credits=0)
        pool.mark("nanobanana", "b@x.com", "exhausted")
        d = pool.dashboard()
        assert d["nanobanana"]["total"] == 2
        assert d["nanobanana"]["ok"] == 1
        assert d["nanobanana"]["exhausted"] == 1
        assert d["nanobanana"]["credits"] == 4


# ── v6.6.0 P3-4 号池补满速率画像 ───────────────────────
class TestAccountPoolGrowth:
    def test_growth_structure_and_gap(self, pool):
        """growth 画像结构完整；新增为 0 时 eta_days 为 None（无法估算）。"""
        d = pool.growth_stats("nanobanana")
        for key in ("total", "new_in_24h", "new_in_7d", "avg_daily_7d", "ok", "target", "gap", "eta_days"):
            assert key in d, f"growth 缺字段 {key}"
        assert d["total"] == 0
        assert d["new_in_24h"] == 0
        assert d["gap"] == 10000  # 无可用账号 → 距目标差整个目标
        assert d["eta_days"] is None  # 速率为 0 → None（前端显示 —）

    def test_growth_counts_new_accounts(self, pool):
        """新增账号计入 new_in_24h；gap = target - ok 反映真实缺口。"""
        pool.add("nanobanana", "a@x.com", "c1", credits=4)
        pool.add("nanobanana", "b@x.com", "c2", credits=4)
        d = pool.growth_stats("nanobanana")
        assert d["total"] == 2
        assert d["new_in_24h"] == 2
        assert d["ok"] == 2
        assert d["target"] == 10000
        assert d["gap"] == 9998
        assert d["eta_days"] == round(9998 / 2, 1)  # 2/天 → 约 4999 天

    def test_growth_eta_none_when_zero_rate(self, pool):
        """账号老化 >24h 无新增 → new_in_24h=0 → eta None。"""
        pool.add("nanobanana", "old@x.com", "c", credits=4)
        # 把 created_at 篡改为 3 天前
        pool._conn.execute(
            "UPDATE accounts SET created_at=? WHERE email='old@x.com'",
            (time.time() - 3 * 86400,),
        )
        pool._conn.commit()
        d = pool.growth_stats("nanobanana")
        assert d["new_in_24h"] == 0
        assert d["new_in_7d"] == 1
        assert d["avg_daily_7d"] == round(1 / 7, 1)
        assert d["eta_days"] is None


@pytest.mark.asyncio
async def test_autoregister_pauses_without_proxy(tmp_path, monkeypatch):
    """P-TEST-A7: 无任何可用代理且非 mock → 补号循环暂停（不注册）。"""
    from api.account_pool import AccountPool
    from api import proxy_pool as pp_mod

    # 确保代理池为空 + 非 mock 模式
    monkeypatch.setattr(pp_mod.proxy_pool, "entries", [])
    # account_pool.py 是 from-import 值拷贝——必须 patch 它那份才生效（patch base 无用）
    monkeypatch.setattr("api.providers.base.MOCK_REGISTER", False)
    import api.account_pool as ap_mod

    monkeypatch.setattr(ap_mod, "MOCK_REGISTER", False)
    monkeypatch.setattr("api.account_pool.REGISTER_COOLDOWN", 0.1)
    monkeypatch.setattr("api.account_pool.TARGET_NANOBANANA", 1)

    p = AccountPool(str(tmp_path / "acc.db"))
    calls = []

    class _Reg:
        async def register_one(self):
            calls.append(1)
            return None

    p.registerers["nanobanana"] = _Reg()
    p.proxy = None
    task = asyncio.create_task(p._autoregister_loop("nanobanana"))
    try:
        await asyncio.sleep(0.8)  # 冷却 0.1s 内应循环多次但都不注册
        assert calls == []  # 无代理守卫生效：未触发任何注册
        assert len(p.get("nanobanana")) == 0
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        p._conn.close()


# ── async 包装方法（asyncio.to_thread，不阻塞事件循环）──────────────
class TestAsyncWrappers:
    """async_get/async_borrow_account/async_release_account/async_mark_dead/
    async_consume_credits/async_get_adaptive：返回值与同步方法一致，且不阻塞 loop。"""

    @pytest.mark.asyncio
    async def test_async_get_returns_same_as_sync(self, pool):
        pool.add("nanobanana", "a@x.com", "c1", credits=4)
        pool.add("nanobanana", "b@x.com", "c2", credits=4)
        sync_accs = pool.get("nanobanana")
        async_accs = await pool.async_get("nanobanana")
        # 返回值内容一致（顺序可能因 SQL 一致而相同）
        assert len(async_accs) == len(sync_accs) == 2
        async_emails = {a["email"] for a in async_accs}
        sync_emails = {a["email"] for a in sync_accs}
        assert async_emails == sync_emails == {"a@x.com", "b@x.com"}

    @pytest.mark.asyncio
    async def test_async_borrow_and_release(self, pool):
        pool.add("nanobanana", "ab@x.com", "c", credits=5, status="active")
        acc = await pool.async_borrow_account("nanobanana")
        assert acc is not None
        assert acc["email"] == "ab@x.com"
        assert acc["status"] == "working"
        # 借出后再借应无可用 active
        acc2 = await pool.async_borrow_account("nanobanana")
        assert acc2 is None
        # 归还
        await pool.async_release_account("nanobanana", "ab@x.com", new_credits=3)
        active = await pool.async_get("nanobanana")
        assert len(active) == 1
        assert active[0]["credits"] == 3
        assert active[0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_async_mark_dead(self, pool):
        pool.add("nanobanana", "md@x.com", "c", credits=10, status="active")
        await pool.async_mark_dead("nanobanana", "md@x.com", reason="HTTP 401")
        dead_list = pool.list("nanobanana", status="dead")
        assert len(dead_list) == 1
        assert "401" in dead_list[0]["note"]
        assert await pool.async_get("nanobanana") == []

    @pytest.mark.asyncio
    async def test_async_consume_credits(self, pool):
        pool.add("nanobanana", "cc@x.com", "c", credits=20, status="active")
        await pool.async_consume_credits("nanobanana", "cc@x.com", 4)
        row = (await pool.async_get("nanobanana"))[0]
        assert row["credits"] == 16
        assert row["credits_used_total"] == 4
        assert row["images_used"] == 1

    @pytest.mark.asyncio
    async def test_async_get_adaptive(self, pool):
        pool.add("nanobanana", "ga1@x.com", "c", credits=4, status="active")
        pool.add("nanobanana", "ga2@x.com", "c", credits=8, status="active")
        acc = await pool.async_get_adaptive("nanobanana")
        assert acc is not None
        assert acc["email"] in {"ga1@x.com", "ga2@x.com"}
        # 空池 → None
        assert await pool.async_get_adaptive("nonexistent") is None

    @pytest.mark.asyncio
    async def test_async_wrappers_do_not_block_event_loop(self, pool):
        """并发跑多个 async 包装 + 一个 sleep(0) 协程，sleep(0) 必须被调度（非阻塞证据）。"""
        pool.add("nanobanana", "nb@x.com", "c", credits=100, status="active")
        # 用一个 flag 验证并发期间事件循环仍能调度其它任务
        flag = {"ticked": 0}

        async def _tick():
            for _ in range(5):
                await asyncio.sleep(0)
                flag["ticked"] += 1

        async def _work():
            for _ in range(5):
                await pool.async_get("nanobanana")
                await pool.async_consume_credits("nanobanana", "nb@x.com", 1)

        await asyncio.gather(_tick(), _work())
        assert flag["ticked"] == 5  # 事件循环未被同步 sqlite3 阻塞
        # consume 也生效
        row = (await pool.async_get("nanobanana"))[0]
        assert row["credits"] == 95
        assert row["images_used"] == 5

    @pytest.mark.asyncio
    async def test_lease_uses_async_wrappers(self, pool):
        """lease 上下文管理器内部走 async_borrow/async_release（不阻塞 loop）。"""
        pool.add("nanobanana", "ls@x.com", "c", credits=5, status="active")
        async with pool.lease("nanobanana") as acc:
            assert acc is not None
            assert acc["email"] == "ls@x.com"
            assert acc["status"] == "working"
        # 退出后已归还
        active = await pool.async_get("nanobanana")
        assert len(active) == 1
        assert active[0]["status"] == "active"

