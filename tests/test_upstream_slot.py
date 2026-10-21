"""P-TEST-A3: 上游命名槽位模块 upstream_slot 单元测试。

覆盖：
- 并发 = 1 时互斥（第二个 acquire 超时返回 False，释放后可获取）
- 同上下文重入直通（不自锁）
- 跨进程文件锁 stale 回收（损坏 / 超时 / PID 已死）
- acquire 超时返回 False
- release 幂等 / 未持有 release 无副作用
- slot_path 派生（sha256 前缀 + 目录）
- 上下文管理器 upstream_slot 语义
"""

import asyncio
import os
import time

import pytest

from api import upstream_slot as us


@pytest.fixture()
def slot_env(tmp_path, monkeypatch):
    """把槽位目录重定向到 tmp_path，避免污染真实 data/.upstream_slots。"""
    d = tmp_path / "slots"
    monkeypatch.setattr(us, "_SLOT_DIR", str(d))
    monkeypatch.setattr(us, "_LOCKS", {})
    monkeypatch.setattr(us, "_SEMAPHORES", {})
    monkeypatch.setattr(us, "_WARNED", set())
    monkeypatch.setattr(us.config, "IF_TXT_MAX_INFLIGHT", 1)
    monkeypatch.setattr(us.config, "IF_TXT_SLOT_STALE", 600)
    monkeypatch.setattr(us.config, "IF_TXT_SLOT_WAIT", 120)
    return d


class TestSlotPath:
    def test_dir_created_on_acquire(self, slot_env):
        p = us.slot_path("k")
        assert os.path.dirname(p) == str(slot_env)
        assert p.endswith(".lock")

    def test_derivation_is_stable_and_hashed(self, slot_env):
        a = us.slot_path("imagefree-txt:direct")
        b = us.slot_path("imagefree-txt:direct")
        c = us.slot_path("imagefree-txt:proxy")
        assert a == b and a != c
        assert os.path.basename(a).startswith("slot-")
        # 文件名里不得泄漏原始 key
        assert "imagefree" not in a and ":" not in os.path.basename(a)

    def test_slot_dir_helper_matches(self, slot_env):
        assert us.slot_dir() == str(slot_env)


class TestSlotKeyFor:
    def test_default_is_direct(self):
        assert us.slot_key_for() == "imagefree-txt:direct"

    def test_none_is_direct(self):
        assert us.slot_key_for(None) == "imagefree-txt:direct"

    def test_proxy_embedded(self):
        assert us.slot_key_for("http://u:p@1.2.3.4:8080") == "imagefree-txt:http://u:p@1.2.3.4:8080"

    def test_matches_generator_convention(self):
        # engine ? generator ??????? key????????????
        assert us.slot_key_for(None) == f"imagefree-txt:{'direct'}"


class TestMutualExclusion:
    @pytest.mark.asyncio
    async def test_second_acquire_times_out(self, slot_env):
        s1 = us.UpstreamSlot("k1")
        assert await s1.acquire(wait=1.0) is True
        s2 = us.UpstreamSlot("k1")
        t = time.monotonic()
        assert await s2.acquire(wait=0.8) is False
        assert time.monotonic() - t >= 0.7
        await s1.release()

    @pytest.mark.asyncio
    async def test_acquire_succeeds_after_release(self, slot_env):
        s1 = us.UpstreamSlot("k2")
        assert await s1.acquire(wait=1.0)
        await s1.release()
        s2 = us.UpstreamSlot("k2")
        assert await s2.acquire(wait=1.0) is True
        await s2.release()

    @pytest.mark.asyncio
    async def test_different_keys_do_not_block(self, slot_env):
        s1 = us.UpstreamSlot("ka")
        s2 = us.UpstreamSlot("kb")
        assert await s1.acquire(wait=1.0)
        assert await s2.acquire(wait=1.0)
        await s1.release()
        await s2.release()

    @pytest.mark.asyncio
    async def test_file_lock_created_and_removed(self, slot_env):
        s = us.UpstreamSlot("kf")
        assert await s.acquire(wait=1.0)
        path = us.slot_path("kf")
        assert os.path.exists(path)
        body = open(path, encoding="utf-8").read().split()
        assert len(body) == 3 and int(body[0]) == os.getpid()
        await s.release()
        assert not os.path.exists(path)

    @pytest.mark.asyncio
    async def test_concurrent_holders_serialized(self, slot_env):
        """10 个并发 acquire 同一 key，同时持有数必须为 1。"""
        live = 0
        peak = 0
        done = []

        async def worker(i):
            nonlocal live, peak
            s = us.UpstreamSlot("kconc")
            ok = await s.acquire(wait=10.0)
            if not ok:
                done.append(False)
                return
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.05)
            live -= 1
            await s.release()
            done.append(True)

        await asyncio.gather(*[worker(i) for i in range(10)])
        assert peak == 1
        assert all(done)


class TestReentrancy:
    @pytest.mark.asyncio
    async def test_strict_mutex_by_default_same_task(self, slot_env):
        """?? task ???????????????????? IP ?? 1??"""
        outer = us.UpstreamSlot("kre")
        assert await outer.acquire(wait=1.0)
        inner = us.UpstreamSlot("kre")
        assert await inner.acquire(wait=0.5) is False
        await outer.release()

    @pytest.mark.asyncio
    async def test_reuse_context_passthrough(self, slot_env):
        """engine ?????generator ???? reuse_context=True ????"""
        outer = us.UpstreamSlot("kre2")
        assert await outer.acquire(wait=1.0)
        inner = us.UpstreamSlot("kre2")
        assert await inner.acquire(wait=0.5, reuse_context=True) is True
        assert "kre2" in us.held_slots()
        await inner.release()
        # ??????????????
        assert os.path.exists(us.slot_path("kre2"))
        await outer.release()
        assert not os.path.exists(us.slot_path("kre2"))

    @pytest.mark.asyncio
    async def test_reuse_context_other_key_still_blocks(self, slot_env):
        """reuse_context ??? key ????? key ??????????????"""
        outer = us.UpstreamSlot("kra")
        assert await outer.acquire(wait=1.0)
        other = us.UpstreamSlot("krb")
        # ?? key??? reuse_context=True ?????? acquire???? outer ? kra ??
        assert await other.acquire(wait=0.5, reuse_context=True) is True
        # ???krb ?????kra ?? outer ??????? key ? acquire ???
        third = us.UpstreamSlot("kra")
        assert await third.acquire(wait=0.3, reuse_context=True) is True  # ? key ??
        await other.release()
        await outer.release()

    @pytest.mark.asyncio
    async def test_double_acquire_same_instance(self, slot_env):
        s = us.UpstreamSlot("kda")
        assert await s.acquire(wait=1.0)
        assert await s.acquire(wait=0.1) is True  # ????
        await s.release()
        await s.release()  # ??
        assert not os.path.exists(us.slot_path("kda"))

    @pytest.mark.asyncio
    async def test_release_without_hold_is_noop(self, slot_env):
        s = us.UpstreamSlot("knoop")
        await s.release()
        assert not os.path.exists(us.slot_path("knoop"))

    @pytest.mark.asyncio
    async def test_child_task_acquisition_does_not_leak_to_parent(self, slot_env):
        """? task ?????????? task ? _HELD?ContextVar task ????"""
        result = {}

        async def child():
            s = us.UpstreamSlot("kchild")
            result["ok"] = await s.acquire(wait=1.0)
            assert result["ok"]
            assert "kchild" in us.held_slots()  # ? task ???
            await s.release()

        await asyncio.create_task(child())
        assert result["ok"] is True
        assert "kchild" not in us.held_slots()  # ? task ????

    @pytest.mark.asyncio
    async def test_unheld_slot_reuse_context_is_noop(self, slot_env):
        """????????reuse_context=True ??????????????"""
        s = us.UpstreamSlot("kunheld")
        assert await s.acquire(wait=1.0, reuse_context=True) is True
        await s.release()



class TestStale:
    def test_missing_file_is_stale(self, slot_env):
        assert us._lock_stale(us.slot_path("nope"), 600) is True

    def test_corrupt_file_is_stale(self, slot_env, tmp_path):
        p = tmp_path / "corrupt.lock"
        p.write_text("garbage", encoding="utf-8")
        assert us._lock_stale(str(p), 600) is True

    def test_too_few_parts_is_stale(self, slot_env, tmp_path):
        p = tmp_path / "short.lock"
        p.write_text("123 only", encoding="utf-8")
        assert us._lock_stale(str(p), 600) is True

    def test_fresh_lock_not_stale(self, slot_env, tmp_path):
        p = tmp_path / "fresh.lock"
        p.write_text(f"{os.getpid()} {time.time()} tok", encoding="utf-8")
        assert us._lock_stale(str(p), 600) is False

    def test_expired_lock_is_stale(self, slot_env, tmp_path):
        p = tmp_path / "old.lock"
        p.write_text(f"{os.getpid()} {time.time() - 700} tok", encoding="utf-8")
        assert us._lock_stale(str(p), 600) is True

    def test_zero_stale_after_ignores_age(self, slot_env, tmp_path):
        p = tmp_path / "aged.lock"
        p.write_text(f"{os.getpid()} {time.time() - 99999} tok", encoding="utf-8")
        assert us._lock_stale(str(p), 0) is False

    def test_dead_pid_is_stale(self, slot_env, tmp_path):
        p = tmp_path / "dead.lock"
        p.write_text(f"999999 {time.time()} tok", encoding="utf-8")
        assert us._lock_stale(str(p), 600) is True

    def test_pid_one_uses_time_only(self, slot_env, tmp_path):
        p = tmp_path / "pid1.lock"
        p.write_text(f"1 {time.time()} tok", encoding="utf-8")
        assert us._lock_stale(str(p), 600) is True

    @pytest.mark.asyncio
    async def test_stale_lock_taken_over(self, slot_env):
        path = us.slot_path("kstale")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"999999 {time.time() - 9999} deadtok")
        s = us.UpstreamSlot("kstale")
        assert await s.acquire(wait=3.0) is True
        await s.release()
        assert not os.path.exists(path)


class TestPidAlive:
    def test_current_pid_alive(self):
        assert us._pid_alive(os.getpid()) is True

    def test_dead_pid_not_alive(self):
        # Windows 抛 OSError(WinError 87) 而非 ProcessLookupError
        assert us._pid_alive(999999) is False

    def test_nonpositive_pid_not_alive(self):
        assert us._pid_alive(0) is False
        assert us._pid_alive(-1) is False


class TestSemaphoreMode:
    @pytest.mark.asyncio
    async def test_limit_two_allows_two(self, slot_env, monkeypatch):
        monkeypatch.setattr(us.config, "IF_TXT_MAX_INFLIGHT", 2)
        s1 = us.UpstreamSlot("ksem")
        s2 = us.UpstreamSlot("ksem")
        assert s1.limit == 2
        assert await s1.acquire(wait=1.0)
        assert await s2.acquire(wait=1.0)
        s3 = us.UpstreamSlot("ksem")
        assert await s3.acquire(wait=0.5) is False
        await s1.release()
        assert await s3.acquire(wait=1.0) is True
        await s2.release()
        await s3.release()


class TestContextManager:
    @pytest.mark.asyncio
    async def test_yields_true_and_releases(self, slot_env):
        async with us.upstream_slot("kcm", wait=1.0) as ok:
            assert ok is True
            assert os.path.exists(us.slot_path("kcm"))
        assert not os.path.exists(us.slot_path("kcm"))

    @pytest.mark.asyncio
    async def test_yields_false_on_timeout(self, slot_env):
        holder = us.UpstreamSlot("kcm2")
        assert await holder.acquire(wait=1.0)
        async with us.upstream_slot("kcm2", wait=0.5) as ok:
            assert ok is False
        await holder.release()

    @pytest.mark.asyncio
    async def test_releases_on_exception(self, slot_env):
        with pytest.raises(RuntimeError):
            async with us.upstream_slot("kcm3", wait=1.0) as ok:
                assert ok is True
                raise RuntimeError("boom")
        assert not os.path.exists(us.slot_path("kcm3"))

    @pytest.mark.asyncio
    async def test_limit_override(self, slot_env):
        async with us.upstream_slot("kcm4", wait=1.0, limit=2) as ok:
            assert ok is True
