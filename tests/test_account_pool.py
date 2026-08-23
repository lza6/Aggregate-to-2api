"""号池（account_pool）与邮箱池（email_pool）单测：持久化/分配/自动补号/签到。"""
import asyncio
import os
import time

import pytest

from api import config

# 测试隔离：临时 DB 路径（fixture 里动态生成）
os.environ.setdefault("IF_ACCOUNT_AUTO", "0")


class _FakeReg:
    """假注册器：register_one 返回固定账号；checkin 返回递增余额。"""
    calls = 0

    async def register_one(self):
        _FakeReg.calls += 1
        return {"email": f"mock{_FakeReg.calls}@m.com", "cookie": "mock-session",
                "password": "p", "credits": 4}

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
        pool.add("minimaxh3", "a@x.com", "cookie1", credits=4)
        pool.add("minimaxh3", "b@x.com", "cookie2", credits=4)
        pool.add("nanobanana", "c@x.com", "cookie3", credits=4)
        mm = pool.get("minimaxh3")
        assert len(mm) == 2
        assert all(a["cookie"] for a in mm)
        assert pool.total_credits("minimaxh3") == 8
        assert pool.total_credits("nanobanana") == 4

    def test_mark_and_credits(self, pool):
        pool.add("minimaxh3", "a@x.com", "c", credits=4)
        pool.update_credits("minimaxh3", "a@x.com", 0)
        assert pool.total_credits("minimaxh3") == 0
        pool.mark("minimaxh3", "a@x.com", "exhausted")
        assert pool.get("minimaxh3") == []  # exhausted 不算可用

    def test_counts(self, pool):
        pool.add("minimaxh3", "a@x.com", "c", credits=4)
        pool.add("minimaxh3", "b@x.com", "c", credits=4, status="exhausted")
        c = pool.counts()
        assert c["minimaxh3"]["ok"] == 1
        assert c["minimaxh3"]["exhausted"] == 1

    def test_dashboard(self, pool):
        pool.add("minimaxh3", "a@x.com", "c", credits=4)
        d = pool.dashboard()
        assert "minimaxh3" in d
        assert d["minimaxh3"]["credits"] == 4


# ── 自动补号 ─────────────────────────────────────
@pytest.mark.asyncio
async def test_autoregister_loop_fills_to_target(tmp_path, monkeypatch):
    from api.account_pool import AccountPool
    from api.proxy_pool import ProxyEntry, proxy_pool
    # 注入一个 residential 代理（无住宅代理时补号循环按安全红线跳过注册）
    proxy_pool.entries.append(ProxyEntry("http://r:r@1.1.1.1:8080", source="residential"))
    p = AccountPool(str(tmp_path / "acc.db"))
    p.registerers["minimaxh3"] = _FakeReg()
    monkeypatch.setattr("api.account_pool.TARGET_MINIMAXH3", 2)
    monkeypatch.setattr("api.account_pool.REGISTER_COOLDOWN", 0.1)  # M5 成功节流缩短，测试快速补满
    # 提高每日上限，让同一个 IP 能被注册两次（代理池默认每 IP 每日只用 1 次）
    monkeypatch.setattr("api.config.IF_PROXY_MAX_USE_PER_DAY", 2)
    task = asyncio.create_task(p._autoregister_loop("minimaxh3"))
    try:
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and len(p.get("minimaxh3")) < 2:
            await asyncio.sleep(0.3)
        assert len(p.get("minimaxh3")) >= 2
        assert p.total_credits("minimaxh3") >= 8
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        proxy_pool.entries = [e for e in proxy_pool.entries if e.url != "http://r:r@1.1.1.1:8080"]
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


# ── 邮箱池 ──────────────────────────────────────
class TestEmailPool:
    @pytest.mark.asyncio
    async def test_allocate_unique_and_record(self, tmp_path, monkeypatch):
        from api.email_pool import EmailPool
        p = EmailPool(str(tmp_path / "email.db"))
        # 网络源打桩：temp-mail/22.do 建箱是真实 HTTP 调用（无 mock 会挂测试），
        # 本用例只验证分配唯一性与记录逻辑——本地 temp.tf 随机源足够
        monkeypatch.setattr(
            p, "_sources",
            [s for s in p._sources if s.name == "temp.tf"])
        a1, _s1 = await p.allocate("minimaxh3")
        a2, _s2 = await p.allocate("minimaxh3")
        assert a1 != a2
        assert "@" in a1 and a1.split("@")[1].count(".") >= 1  # 合法邮箱（local@domain.tld）
        p.record(a1, "minimaxh3", "ok")
        assert p.registered_providers(a1) == ["minimaxh3"]
        # 已用邮箱不再分配
        a3, _s3 = await p.allocate("minimaxh3")
        assert a3 not in (a1, a2)
        p._conn.close()

    @pytest.mark.asyncio
    async def test_stats(self, tmp_path, monkeypatch):
        from api.email_pool import EmailPool
        p = EmailPool(str(tmp_path / "email.db"))
        # 同上：打桩网络源，只留本地 temp.tf
        monkeypatch.setattr(
            p, "_sources",
            [s for s in p._sources if s.name == "temp.tf"])
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
        for prov in ("minimaxh3", "nanobanana"):
            assert prov in d
            entry = d[prov]
            for key in ("total", "ok", "exhausted", "registering", "credits", "target", "auto_register"):
                assert key in entry, f"{prov} 缺字段 {key}"
        assert d["minimaxh3"]["target"] == 500
        assert d["nanobanana"]["target"] == 500
        assert d["minimaxh3"]["auto_register"] is False  # 未注入注册器

    def test_dashboard_counts_reflect_state(self, pool):
        pool.add("minimaxh3", "a@x.com", "c1", credits=4)
        pool.add("minimaxh3", "b@x.com", "c2", credits=0)
        pool.mark("minimaxh3", "b@x.com", "exhausted")
        d = pool.dashboard()
        assert d["minimaxh3"]["total"] == 2
        assert d["minimaxh3"]["ok"] == 1
        assert d["minimaxh3"]["exhausted"] == 1
        assert d["minimaxh3"]["credits"] == 4


@pytest.mark.asyncio
async def test_autoregister_pauses_without_proxy(tmp_path, monkeypatch):
    """P-TEST-A7: 无任何可用代理且非 mock → 补号循环暂停（不注册）。"""
    from api.account_pool import AccountPool
    from api import proxy_pool as pp_mod

    # 确保代理池为空 + 非 mock 模式
    monkeypatch.setattr(pp_mod.proxy_pool, "entries", [])
    monkeypatch.setattr("api.providers.base.MOCK_REGISTER", False)
    monkeypatch.setattr("api.account_pool.REGISTER_COOLDOWN", 0.1)
    monkeypatch.setattr("api.account_pool.TARGET_MINIMAXH3", 1)

    p = AccountPool(str(tmp_path / "acc.db"))
    calls = []

    class _Reg:
        async def register_one(self):
            calls.append(1)
            return None

    p.registerers["minimaxh3"] = _Reg()
    p.proxy = None
    task = asyncio.create_task(p._autoregister_loop("minimaxh3"))
    try:
        await asyncio.sleep(0.8)  # 冷却 0.1s 内应循环多次但都不注册
        assert calls == []  # 无代理守卫生效：未触发任何注册
        assert len(p.get("minimaxh3")) == 0
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        p._conn.close()
