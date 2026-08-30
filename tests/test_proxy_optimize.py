"""代理池优化策略单测：use_count 递增冷却、优先选未使用 IP、每日限制、24h 重置、
trace 回填（v6.7.x）。"""

import os
import time

import pytest

os.environ.setdefault("IF_ACCOUNT_AUTO", "0")

from api.config import IF_PROXY_MAX_USE_PER_DAY
from api.proxy_pool import ProxyEntry, ProxyPool, _cooldown_for


class TestProxyEntry:
    def test_use_count_starts_zero(self):
        e = ProxyEntry("http://u:p@1.2.3.4:8080")
        assert e.use_count == 0

    def test_cooling_property(self):
        e = ProxyEntry("http://u:p@1.2.3.4:8080")
        assert not e.cooling  # 刚创建，未冷却
        e.cooldown_until = time.time() + 9999
        assert e.cooling

    def test_available_after_use_count_exceeds_max(self):
        """use_count >= IF_PROXY_MAX_USE_PER_DAY 时不可用。"""
        e = ProxyEntry("http://u:p@1.2.3.4:8080")
        e.use_count = IF_PROXY_MAX_USE_PER_DAY  # 默认 1
        now = time.time()
        # 不在冷却，但已超每日限额
        assert not e.available(now)

    def test_24h_reset_use_count(self):
        """24h 后 use_count 归零。"""
        e = ProxyEntry("http://u:p@1.2.3.4:8080")
        e.use_count = 5
        # 模拟 24h+ 后的时间
        far_future = time.time() + 86401
        assert e.available(far_future)
        assert e.use_count == 0

    def test_cooldown_map_values(self):
        """USE_COOLDOWN_MAP 默认值：1->0, 2->30, 3->90, 4->300, 5->900。"""
        assert _cooldown_for(1) == 0
        assert _cooldown_for(2) == 30
        assert _cooldown_for(3) == 90
        assert _cooldown_for(4) == 300
        assert _cooldown_for(5) == 900
        # 超过映射长度取最后一个
        assert _cooldown_for(99) == 900

    def test_cooldown_map_from_env(self):
        """环境变量可覆盖 USE_COOLDOWN_MAP。"""
        # 默认值已在模块级解析，此处验证函数行为
        assert _cooldown_for(1) == 0  # 第 1 次不用等
        assert _cooldown_for(2) == 30  # 第 2 次等 30s


class TestProxyPool:
    @pytest.mark.asyncio
    async def test_acquire_prefers_unused(self):
        """优先选 use_count == 0 的 IP。"""
        pool = ProxyPool()
        pool.entries = [
            ProxyEntry("http://u:p@1.1.1.1:8080"),
            ProxyEntry("http://u:p@2.2.2.2:8080"),
            ProxyEntry("http://u:p@3.3.3.3:8080"),
        ]
        # 标记 2.2.2.2 已用过
        pool.entries[1].use_count = 1
        pool.entries[1].last_used_at = time.time() - 100

        url = await pool.acquire()
        # 应该选第一个未用过的 (1.1.1.1)
        assert "1.1.1.1" in url

    @pytest.mark.asyncio
    async def test_acquire_after_all_used_chooses_earliest_cooldown(self):
        """全部用过一轮后，选冷却最早结束的。"""
        pool = ProxyPool()
        pool.entries = [
            ProxyEntry("http://u:p@1.1.1.1:8080"),
            ProxyEntry("http://u:p@2.2.2.2:8080"),
            ProxyEntry("http://u:p@3.3.3.3:8080"),
        ]
        now = time.time()
        for e in pool.entries:
            e.use_count = 1
            e.last_used_at = now
        # 1.1.1.1 冷却最早结束
        pool.entries[0].cooldown_until = now
        # 2.2.2.2 冷却中
        pool.entries[1].cooldown_until = now + 999
        # 3.3.3.3 冷却中
        pool.entries[2].cooldown_until = now + 888

        url = await pool.acquire()
        assert "1.1.1.1" in url

    @pytest.mark.asyncio
    async def test_acquire_use_count_increments(self):
        """acquire 后 use_count +1。"""
        pool = ProxyPool()
        pool.entries = [ProxyEntry("http://u:p@1.1.1.1:8080")]
        await pool.acquire()
        assert pool.entries[0].use_count == 1
        # 使用后冷却应该被设置
        assert pool.entries[0].cooldown_until > 0

    @pytest.mark.asyncio
    async def test_acquire_cooldown_set_after_use(self):
        """使用后按 USE_COOLDOWN_MAP 设定冷却时间。"""
        pool = ProxyPool()
        pool.entries = [ProxyEntry("http://u:p@1.1.1.1:8080")]
        now = time.time()
        await pool.acquire()  # use_count -> 1, cooldown = 0 (不用等)
        assert pool.entries[0].cooldown_until <= now + 1  # 约等于 now

        # 再次使用（但为了测试，手动改 use_count 然后 acquire）
        # 先让可用
        pool.entries[0].cooldown_until = 0
        pool.entries[0].use_count = 1  # 第 2 次使用
        pool.entries[0].last_used_at = now - 100
        now2 = time.time()
        await pool.acquire()
        # 第 2 次使用后冷却 = 30s
        assert pool.entries[0].cooldown_until >= now2 + 25

    @pytest.mark.asyncio
    async def test_cooldown_on_use_respects_map(self):
        """每次使用后冷却时间按 use_count 递增。"""
        pool = ProxyPool()
        pool.entries = [ProxyEntry("http://u:p@1.1.1.1:8080")]
        # 模拟第 5 次使用
        pool.entries[0].use_count = 4
        pool.entries[0].cooldown_until = 0
        now = time.time()
        await pool.acquire()  # use_count -> 5, cooldown = 900
        assert pool.entries[0].cooldown_until >= now + 890

    @pytest.mark.asyncio
    async def test_mark_failure_does_not_increment_use_count(self):
        """失败不增加 use_count。"""
        e = ProxyEntry("http://u:p@1.1.1.1:8080")
        pool = ProxyPool()
        pool.entries = [e]
        e.use_count = 2
        await pool.mark_failure(e.url, rate_limited=True)
        assert e.use_count == 2  # 不变

    @pytest.mark.asyncio
    async def test_mark_failure_429_sets_cooldown(self):
        """429 时按递增冷却设定 cooldown_until。"""
        e = ProxyEntry("http://u:p@1.1.1.1:8080")
        pool = ProxyPool()
        pool.entries = [e]
        e.use_count = 2  # 第 2 次后失败，下次用是第 3 次等级
        now = time.time()
        await pool.mark_failure(e.url, rate_limited=True)
        # 第 3 次等级冷却 = 90s
        assert e.cooldown_until >= now + 85

    @pytest.mark.asyncio
    async def test_mark_failure_non_429_sets_short_cooldown(self):
        """非 429 失败冷却 30s。"""
        e = ProxyEntry("http://u:p@1.1.1.1:8080")
        pool = ProxyPool()
        pool.entries = [e]
        now = time.time()
        await pool.mark_failure(e.url, rate_limited=False)
        assert e.cooldown_until >= now + 25

    @pytest.mark.asyncio
    async def test_acquire_returns_none_when_empty(self):
        pool = ProxyPool()
        assert await pool.acquire() is None

    @pytest.mark.asyncio
    async def test_acquire_respects_prefer_source(self):
        pool = ProxyPool()
        pool.entries = [
            ProxyEntry("http://u:p@1.1.1.1:8080", source="free"),
            ProxyEntry("http://u:p@2.2.2.2:8080", source="residential"),
        ]
        url = await pool.acquire(prefer_source="residential")
        assert "2.2.2.2" in url

    @pytest.mark.asyncio
    async def test_all_entries_cooling_falls_back(self):
        """全在冷却时返回最早结束冷却的。"""
        pool = ProxyPool()
        now = time.time()
        pool.entries = [
            ProxyEntry("http://u:p@1.1.1.1:8080"),
            ProxyEntry("http://u:p@2.2.2.2:8080"),
        ]
        for e in pool.entries:
            e.cooldown_until = now + 999
        pool.entries[0].cooldown_until = now + 100  # 最早结束
        url = await pool.acquire()
        assert "1.1.1.1" in url

    def test_snapshot_includes_use_count_and_cooling(self):
        e = ProxyEntry("http://u:p@1.1.1.1:8080")
        pool = ProxyPool()
        pool.entries = [e]
        e.use_count = 3
        snap = pool.snapshot()
        top = snap["top"][0]
        assert top["use_count"] == 3
        assert top["cooling"] is False
        assert top["cooldown_seconds"] == 0

    @pytest.mark.asyncio
    async def test_max_use_per_day_blocks_reuse(self):
        """IF_PROXY_MAX_USE_PER_DAY=1 时，同一 IP 用完一次后当天不可用。"""
        pool = ProxyPool()
        pool.entries = [ProxyEntry("http://u:p@1.1.1.1:8080")]
        # 先使用一次
        await pool.acquire()
        assert pool.entries[0].use_count == 1
        # 现在可用检查应该返回 False（已达每日限额）
        assert not pool.entries[0].available(time.time())


# ── trace 回填（v6.7.x）──────────────────────────
class TestApplyTraceResult:
    @pytest.mark.asyncio
    async def test_real_exit_backfills_exit_ip_and_clears_fails(self):
        """real_exit=True 时回填 exit_ip/trace_ts/colo 并清零 consecutive_fails。"""
        e = ProxyEntry("http://2.2.2.2:80", source="free")
        e.consecutive_fails = 3
        pool = ProxyPool()
        pool.entries = [e]
        geo = {
            "exit_ip": "9.9.9.9",
            "real_exit": True,
            "colo": "SJC",
            "code": "US",
            "name": "美国",
            "emoji": "🇺🇸",
            "desc": "美国 · Cloudflare SJC",
            "ts": time.time(),
            "http": "HTTP/2",
            "tls": "TLSv1.3",
        }
        await pool.apply_trace_result(e.url, geo)
        assert e.exit_ip == "9.9.9.9"
        assert e.real_exit is True
        assert e.trace_ts == geo["ts"]
        assert e.trace_colo == "SJC"
        assert e.consecutive_fails == 0  # real_exit → 清零

    @pytest.mark.asyncio
    async def test_fake_proxy_increments_fails(self):
        """real_exit=False（出口 IP == host，疑似假代理）时 consecutive_fails +1。"""
        e = ProxyEntry("http://2.2.2.2:80", source="free")
        e.consecutive_fails = 1
        pool = ProxyPool()
        pool.entries = [e]
        geo = {
            "exit_ip": "2.2.2.2",
            "real_exit": False,
            "colo": "SJC",
            "code": "US",
            "name": "美国",
            "emoji": "🇺🇸",
            "desc": "美国",
            "ts": time.time(),
            "http": "",
            "tls": "",
        }
        await pool.apply_trace_result(e.url, geo)
        assert e.exit_ip == "2.2.2.2"
        assert e.real_exit is False
        assert e.consecutive_fails == 2  # 增量
        assert e.trace_ts > 0

    @pytest.mark.asyncio
    async def test_unknown_url_is_noop(self):
        """未匹配条目时安全返回（无副作用）。"""
        pool = ProxyPool()
        pool.entries = [ProxyEntry("http://1.1.1.1:80", source="free")]
        geo = {"exit_ip": "9.9.9.9", "real_exit": True, "ts": time.time()}
        await pool.apply_trace_result("http://9.9.9.9:9999", geo)
        assert pool.entries[0].exit_ip == ""  # 未被改动


class TestSnapshotTraceFields:
    def test_snapshot_exposes_exit_ip_real_exit_colo_when_traced(self):
        """trace 过的条目 snapshot 透出 exit_ip/real_exit/colo + trace_ts 覆盖 latency。"""
        e = ProxyEntry("http://2.2.2.2:80", source="free")
        e.trace_ts = time.time() - 10
        e.exit_ip = "9.9.9.9"
        e.real_exit = True
        e.trace_colo = "SJC"
        pool = ProxyPool()
        pool.entries = [e]
        snap = pool.snapshot()
        item = snap["items"][0]
        assert item["exit_ip"] == "9.9.9.9"
        assert item["real_exit"] is True
        assert item["colo"] == "SJC"
        assert item["trace_ts"] == e.trace_ts
        # trace_ts 覆盖 md5 假 latency：checked_ago_seconds 接近 10（探测距今）
        assert 9 <= item["checked_ago_seconds"] <= 15

    def test_snapshot_without_trace_uses_md5_latency(self):
        """未 trace 的条目 snapshot 不带 exit_ip/real_exit/colo，latency 走 md5。"""
        e = ProxyEntry("http://2.2.2.2:80", source="free")
        pool = ProxyPool()
        pool.entries = [e]
        snap = pool.snapshot()
        item = snap["items"][0]
        assert "exit_ip" not in item
        assert "real_exit" not in item
        assert "colo" not in item
        assert item["latency_ms"] > 0
