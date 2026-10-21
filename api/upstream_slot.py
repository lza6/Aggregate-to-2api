"""文生图上游并发槽（P0-并发闸门）。

背景：imagefree.net 对免费任务按**出口 IP** 硬限「同时在途 1 个」——并发提交时上游直接回
``You already have a free image task in progress. Please wait for it to finish...``。

图生图侧已有 ``_EDIT_LOCK`` + 跨进程文件锁（dispatch_edit.py）；文生图侧此前无任何等价
闸门，IF_WORKERS 并发消费时必然撞上游，且该错误被 RetryPolicy 当普通 transient
（退避 1.2s/4.8s）处理，3 次即耗尽进 DLQ。

本模块提供**通用命名槽位**，语义与图生图锁一致：
- 进程内：按 key 缓存的 ``asyncio.Lock``（并发上限 = IF_TXT_MAX_INFLIGHT）
- 跨进程：``O_EXCL`` 文件锁（``<DB 同级>/.upstream_slots/slot-<sha256(key)[:16]>.lock``），
  内容 ``pid ts token``，支持 PID 存活探测 + 超时回收，防死进程留孤儿锁
- 并发上限 > 1 时退化为纯进程内信号量（文件锁不支持 N 槽语义，仅告警一次）

两种用法：

1. 显式句柄（engine 用：需要在 token 获取【之前】占槽，跨多步持有）::

       slot = UpstreamSlot("imagefree-txt:direct")
       if not await slot.acquire():
           ...  # 等槽超时
       try:
           ...
       finally:
           await slot.release()

2. 上下文管理器（generator 用：短临界区）::

       async with upstream_slot(slot_key_for(proxy), reuse_context=True) as ok:
           if not ok:
               ...

同 key 重入直通：同一任务上下文已持有该槽时，内层 acquire 立即返回 True，由最外层释放
（engine 外层占槽 → generate_once 内层直通，不会自锁）。
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import AsyncIterator

from . import config

log = logging.getLogger("upstream_slot")

__all__ = [
    "UpstreamSlot",
    "upstream_slot",
    "slot_dir",
    "slot_path",
    "slot_key_for",
    "held_slots",
]

_SLOT_DIR = os.path.join(os.path.dirname(config.DB_FILE) or ".", ".upstream_slots")
_LOCKS: dict[str, asyncio.Lock] = {}
_SEMAPHORES: dict[tuple[str, int], asyncio.Semaphore] = {}
_WARNED: set[str] = set()

# 当前任务上下文已持有的槽位 key 集合（重入检测，见模块 docstring）。
_HELD: ContextVar[frozenset[str]] = ContextVar("upstream_slot_held", default=frozenset())


def held_slots() -> frozenset[str]:
    """当前上下文已持有的槽位 key（只读，供诊断/测试）。"""
    return _HELD.get()


def slot_dir() -> str:
    """槽位锁文件目录（与 DB 同级的隐藏目录）。"""
    return _SLOT_DIR


def slot_key_for(proxy: str | None = None) -> str:
    """由出口代理派生文生图槽位 key。engine 与 generator 必须共用本函数，
    否则两边的 key 一旦不一致，外层占的槽就挡不住内层，重入直通也会失效。
    """
    return f"imagefree-txt:{proxy or 'direct'}"


def slot_path(key: str) -> str:
    """按 key 派生锁文件路径（sha256 截断 16 hex，避免非法文件名字符）。"""
    safe = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(_SLOT_DIR, f"slot-{safe}.lock")


def _local_lock(key: str) -> asyncio.Lock:
    """进程内锁（按 key 缓存；同一事件循环内互斥）。"""
    lock = _LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[key] = lock
    return lock


def _local_semaphore(key: str, limit: int) -> asyncio.Semaphore:
    """进程内信号量（limit > 1 时使用）。"""
    skey = (key, limit)
    sem = _SEMAPHORES.get(skey)
    if sem is None:
        sem = asyncio.Semaphore(limit)
        _SEMAPHORES[skey] = sem
    return sem


def _lock_stale(path: str, stale_after: float) -> bool:
    """锁文件是否可回收（损坏 / 超过 stale_after / 持有进程已死）。"""
    try:
        with open(path, encoding="utf-8") as f:
            parts = f.read().split()
        if len(parts) < 3:
            return True
        pid, ts = int(parts[0]), float(parts[1])
    except (OSError, ValueError, IndexError):
        return True
    if stale_after > 0 and time.time() - ts > stale_after:
        return True
    if pid <= 1:
        # 容器内 PID 1 探测会得 PermissionError，按时间判定（同 dispatch_edit 处理）
        return True
    return not _pid_alive(pid)


def _pid_alive(pid: int) -> bool:
    """跨平台判断 PID 是否存活。

    POSIX：``os.kill(pid, 0)`` -> ProcessLookupError=不存在，PermissionError=存在但无权限
    Windows：不存在的 PID 抛 ``OSError(WinError 87 / EINVAL)`` 而**不是**
    ProcessLookupError，必须显式识别；否则残留锁会直接抛异常打断 acquire。
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as e:
        if getattr(e, "winerror", None) == 87 or e.errno == errno.EINVAL:
            return False
        # 其它 OSError（EACCES 等）视为存活，交给 stale_after 时间兜底
        return True
    return True


def _try_create_file_lock(path: str) -> str | None:
    """尝试独占创建锁文件，成功返回持有 token，已被占用返回 None。"""
    os.makedirs(_SLOT_DIR, exist_ok=True)
    try:
        token = uuid.uuid4().hex
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, f"{os.getpid()} {time.time()} {token}".encode())
        finally:
            os.close(fd)
        return token
    except FileExistsError:
        return None


def _release_file_lock(path: str, token: str | None) -> None:
    """释放文件锁：仅当锁文件仍属于本 token 时删除，防误删他人新锁。"""
    if not token:
        return
    try:
        with open(path, encoding="utf-8") as f:
            parts = f.read().split()
        if len(parts) >= 3 and parts[2] == token:
            os.unlink(path)
    except OSError:
        pass


class UpstreamSlot:
    """上游命名槽位句柄：``acquire()`` / ``release()`` 成对使用。

    key: 槽位名（文生图按出口派生 ``imagefree-txt:<proxy|direct>``）
    limit: 并发上限，None → config.IF_TXT_MAX_INFLIGHT（=1 时启用跨进程文件锁）
    """

    def __init__(self, key: str, limit: int | None = None) -> None:
        self.key = key
        self.limit = int(config.IF_TXT_MAX_INFLIGHT) if limit is None else int(limit)
        if self.limit < 1:
            self.limit = 1
        self._held = False
        self._file_token: str | None = None
        self._sem: asyncio.Semaphore | None = None
        self._lock: asyncio.Lock | None = None
        self._ctx_tok = None

    async def acquire(self, wait: float | None = None, reuse_context: bool = False) -> bool:
        """占槽：拿到返回 True，等待超时返回 False（幂等：重复 acquire 直接 True）。

        默认**严格互斥**——同一 asyncio task 里两个独立实例也会互斥（上游按出口 IP
        硬限 1，“上下文里已占” ≠ “本次可以放行”）。

        ``reuse_context=True`` 仅供「外层已占槽、内层必须复用同一槽」
        的嵌套调用（engine 外层占槽 -> generator 内层提交）；此时同 key 直通，
        不落文件、不置 ``_held``，内层 release 空转（不会误放外层槽位）。
        """
        if self._held:
            return True
        if reuse_context and self.key in _HELD.get():
            return True
        if wait is None:
            wait = float(config.IF_TXT_SLOT_WAIT)
        timeout = wait if wait and wait > 0 else None

        if self.limit > 1:
            if self.key not in _WARNED:
                _WARNED.add(self.key)
                log.warning(
                    "槽位 %s 并发上限=%d（>1）：仅进程内生效，多实例部署下跨进程不互斥",
                    self.key,
                    self.limit,
                )
            self._sem = _local_semaphore(self.key, self.limit)
            try:
                await asyncio.wait_for(self._sem.acquire(), timeout=timeout)
            except (TimeoutError, asyncio.TimeoutError):
                self._sem = None
                return False
            self._held = True
            return True

        self._lock = _local_lock(self.key)
        deadline = time.monotonic() + timeout if timeout is not None else None
        try:
            if deadline is None:
                await self._lock.acquire()
            else:
                await asyncio.wait_for(self._lock.acquire(), timeout=max(0.0, deadline - time.monotonic()))
        except (TimeoutError, asyncio.TimeoutError):
            self._lock = None
            return False

        path = slot_path(self.key)
        remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
        token = await self._acquire_file_lock(path, remaining)
        if token is None:
            self._lock.release()
            self._lock = None
            return False

        self._file_token = token
        self._held = True
        self._ctx_tok = _HELD.set(_HELD.get() | {self.key})
        return True

    async def _acquire_file_lock(self, path: str, wait: float | None) -> str | None:
        """跨进程拿锁（轮询 O_EXCL + stale 回收），超时返回 None。"""
        deadline = time.monotonic() + wait if wait and wait > 0 else None
        while True:
            token = _try_create_file_lock(path)
            if token is not None:
                return token
            if _lock_stale(path, float(config.IF_TXT_SLOT_STALE)):
                try:
                    os.unlink(path)
                except OSError:
                    pass
                continue
            if deadline is not None and time.monotonic() > deadline:
                return None
            await asyncio.sleep(0.5)

    async def release(self) -> None:
        """释放槽位（幂等）。"""
        if not self._held:
            return
        self._held = False
        if self._file_token is not None:
            _release_file_lock(slot_path(self.key), self._file_token)
            self._file_token = None
        if self._ctx_tok is not None:
            try:
                _HELD.reset(self._ctx_tok)
            except ValueError:
                pass
            self._ctx_tok = None
        if self._sem is not None:
            self._sem.release()
            self._sem = None
        if self._lock is not None:
            if self._lock.locked():
                self._lock.release()
            self._lock = None

    async def __aenter__(self) -> bool:
        return await self.acquire()

    async def __aexit__(self, *exc: object) -> None:
        await self.release()


@asynccontextmanager
async def upstream_slot(
    key: str,
    wait: float | None = None,
    limit: int | None = None,
    reuse_context: bool = False,
) -> AsyncIterator[bool]:
    """持有上游命名槽位；``yield`` 值为是否拿到槽位（False=等待超时）。

    不抛异常（避免把可恢复的排队变成任务失败），失败文案由调用方决定。
    """
    slot = UpstreamSlot(key, limit=limit)
    ok = await slot.acquire(wait, reuse_context=reuse_context)
    try:
        yield ok
    finally:
        await slot.release()
