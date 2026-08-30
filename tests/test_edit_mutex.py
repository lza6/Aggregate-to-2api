"""P-TEST-A2: 图生图互斥与 _EditProxyPool 特征测试。

锁定现有行为：
- _EditProxyPool：acquire/release 信号量、lock_for per-代理锁、enabled 开关
- _is_edit_slot_wedged：上游并发槽占用判定（英文串匹配）
- _edit_mutex_stale：锁文件损坏/超时/PID 判定
- _acquire/_release_edit_mutex：文件锁获取与 token 释放
"""

import asyncio
import os
import tempfile
import time

import pytest

_tmp_db = tempfile.mktemp(suffix=".db")
os.environ["IF_DB_FILE"] = _tmp_db
os.environ["IF_ACCOUNT_AUTO"] = "0"
os.environ["IF_MOCK_REGISTER"] = "1"

from api import config  # noqa: E402
from api.dispatch_edit import (  # noqa: E402
    _EDIT_MUTEX_DIR,
    _EditProxyPool,
    _acquire_edit_mutex,
    _edit_mutex_path,
    _edit_mutex_stale,
    _is_edit_slot_wedged,
    _release_edit_mutex,
)


class TestIsEditSlotWedged:
    def test_already_have_string(self):
        assert _is_edit_slot_wedged(Exception("You already have an image editing task")) is True

    def test_task_in_progress(self):
        assert _is_edit_slot_wedged(Exception("429: task in progress")) is True

    def test_case_insensitive(self):
        assert _is_edit_slot_wedged(Exception("Task In Progress")) is True

    def test_other_errors_not_wedged(self):
        assert _is_edit_slot_wedged(Exception("500 internal error")) is False
        assert _is_edit_slot_wedged(Exception("upload failed")) is False
        assert _is_edit_slot_wedged(None) is False


class TestEditMutexStale:
    def test_missing_file_is_stale(self):
        assert _edit_mutex_stale(os.path.join(_EDIT_MUTEX_DIR, "edit-nonexistent.lock")) is True

    def test_corrupt_file_is_stale(self, tmp_path):
        p = tmp_path / "corrupt.lock"
        p.write_text("garbage", encoding="utf-8")
        assert _edit_mutex_stale(str(p)) is True

    def test_too_few_parts_is_stale(self, tmp_path):
        p = tmp_path / "short.lock"
        p.write_text("123 only", encoding="utf-8")
        assert _edit_mutex_stale(str(p)) is True

    def test_fresh_lock_not_stale(self, tmp_path):
        p = tmp_path / "fresh.lock"
        p.write_text(f"{os.getpid()} {time.time()} tok", encoding="utf-8")
        assert _edit_mutex_stale(str(p)) is False

    def test_expired_lock_is_stale(self, tmp_path):
        old = time.time() - config.EDIT_LOCK_MAX_AGE - 10
        p = tmp_path / "old.lock"
        p.write_text(f"{os.getpid()} {old} tok", encoding="utf-8")
        assert _edit_mutex_stale(str(p)) is True


class TestFileMutexAcquireRelease:
    @pytest.mark.asyncio
    async def test_acquire_and_release(self):
        token = await _acquire_edit_mutex("test-key-a", timeout=2.0)
        assert token and token != "noop"
        path = _edit_mutex_path("test-key-a")
        assert os.path.exists(path)
        _release_edit_mutex("test-key-a", token)
        assert not os.path.exists(path)

    @pytest.mark.asyncio
    async def test_second_acquire_blocks_then_succeeds_after_release(self):
        t1 = await _acquire_edit_mutex("test-key-b", timeout=2.0)
        assert t1
        # 第二个拿锁在短时间内应超时（锁被占）
        t2 = await _acquire_edit_mutex("test-key-b", timeout=1.5)
        assert t2 is None
        _release_edit_mutex("test-key-b", t1)
        # 释放后可再拿
        t3 = await _acquire_edit_mutex("test-key-b", timeout=2.0)
        assert t3
        _release_edit_mutex("test-key-b", t3)

    @pytest.mark.asyncio
    async def test_wrong_token_no_delete(self):
        t1 = await _acquire_edit_mutex("test-key-c", timeout=2.0)
        assert t1
        _release_edit_mutex("test-key-c", "wrong-token")
        assert os.path.exists(_edit_mutex_path("test-key-c"))  # 他人 token 不误删
        _release_edit_mutex("test-key-c", t1)

    @pytest.mark.asyncio
    async def test_stale_lock_taken_over(self, tmp_path, monkeypatch):
        # 预置一个过期锁文件 → 新 acquire 应清理并获得锁
        path = _edit_mutex_path("test-key-d")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        old = time.time() - config.EDIT_LOCK_MAX_AGE - 10
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"999999 {old} deadtoken")
        token = await _acquire_edit_mutex("test-key-d", timeout=2.0)
        assert token
        _release_edit_mutex("test-key-d", token)


class TestEditProxyPool:
    def test_disabled_without_file(self):
        pool = _EditProxyPool()
        assert pool.enabled is False

    def test_enabled_with_proxies_and_parallel(self, tmp_path, monkeypatch):
        f = tmp_path / "proxies.txt"
        f.write_text("http://u:p@1.2.3.4:8080\nhttp://u:p@5.6.7.8:8080\n# comment\n\n", encoding="utf-8")
        monkeypatch.setattr(config, "EDIT_PROXY_FILE", str(f))
        monkeypatch.setattr(config, "EDIT_PROXY_PARALLEL", 2)
        monkeypatch.setattr(config, "IF_EDIT_PROXY_MAX_INFLIGHT", 2)
        pool = _EditProxyPool()
        assert pool.enabled is True
        assert len(pool.proxies) == 2

    @pytest.mark.asyncio
    async def test_acquire_returns_none_when_disabled(self):
        pool = _EditProxyPool()
        assert await pool.acquire_proxy() is None

    def test_release_none_noop(self):
        pool = _EditProxyPool()
        pool.release_proxy(None)  # 不抛即过

    @pytest.mark.asyncio
    async def test_acquire_release_cycle(self, tmp_path, monkeypatch):
        f = tmp_path / "proxies.txt"
        f.write_text("http://u:p@1.1.1.1:80\nhttp://u:p@2.2.2.2:80\n", encoding="utf-8")
        monkeypatch.setattr(config, "EDIT_PROXY_FILE", str(f))
        monkeypatch.setattr(config, "EDIT_PROXY_PARALLEL", 2)
        monkeypatch.setattr(config, "IF_EDIT_PROXY_MAX_INFLIGHT", 1)
        pool = _EditProxyPool()
        p1 = await pool.acquire_proxy()
        assert p1 in pool.proxies
        # inflight=1：占满后第二个 acquire 应阻塞（轮询 0.5s 内拿不到）
        try:
            await asyncio.wait_for(pool.acquire_proxy(), timeout=0.5)
            blocked = False
        except asyncio.TimeoutError:
            blocked = True
        assert blocked
        pool.release_proxy(p1)
        p2 = await asyncio.wait_for(pool.acquire_proxy(), timeout=1.0)
        pool.release_proxy(p2)

    def test_lock_for_per_proxy(self):
        pool = _EditProxyPool()
        l1 = pool.lock_for("http://p1")
        l2 = pool.lock_for("http://p2")
        assert l1 is not l2
        assert pool.lock_for("http://p1") is l1  # 同代理同锁实例
