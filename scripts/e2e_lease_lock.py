"""图生图租约锁 E2E 验证：并发竞争同一 key，仅一个持有者成功。

用法：
    python scripts/e2e_lease_lock.py            # 使用临时 DB
    IF_EDIT_LEASE_ENABLED=1 python -m pytest tests/test_edit_lease.py -v
"""

import asyncio
import os
import tempfile

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("IF_ACCOUNT_AUTO", "0")
os.environ.setdefault("IF_MOCK_REGISTER", "1")
os.environ["IF_EDIT_LEASE_ENABLED"] = "1"

from api import config
from api.dispatch_edit import _acquire_edit_lock, _EDIT_LEASE_STORE, _release_edit_lock


async def main() -> None:
    key = "e2e-lease-key"
    holder_a, holder_b = "proc-A", "proc-B"
    tok_a = await _acquire_edit_lock(key, holder_a, timeout=3.0)
    assert tok_a, "holder A 应获得锁"
    print(f"[OK] holder A 获取锁: {tok_a[:8]}")

    tok_b = await _acquire_edit_lock(key, holder_b, timeout=1.5)
    assert tok_b is None, "holder B 在 A 持有期间应拿不到锁"
    print("[OK] holder B 被阻塞")

    await _release_edit_lock(key, tok_a)
    tok_c = await _acquire_edit_lock(key, holder_b, timeout=3.0)
    assert tok_c, "holder A 释放后 B 应能获取锁"
    print(f"[OK] holder B 在释放后获取锁: {tok_c[:8]}")
    await _release_edit_lock(key, tok_c)

    # 异常宕机模拟：不释放直接丢弃 → 无续租 → TTL 后过期
    tok_d = await _acquire_edit_lock(key, "holder-C", timeout=3.0)
    assert tok_d
    # 不释放，模拟崩溃
    await asyncio.sleep(config.EDIT_LEASE_TTL + 1)
    tok_e = await _acquire_edit_lock(key, "holder-D", timeout=3.0)
    assert tok_e, "无续租的锁应在 TTL 后自动过期"

    print(f"[OK] 异常宕机后锁自动过期，holder D 获取锁: {tok_e[:8]}")
    print("E2E 租约锁验证全部通过 [OK]")
    # 关闭租约锁连接，让 asyncio.run 能干净退出（否则 aiosqlite 线程使 shutdown 挂起）
    await _EDIT_LEASE_STORE.close()


if __name__ == "__main__":
    os.environ["IF_DB_FILE"] = tempfile.mktemp(suffix=".db")
    asyncio.run(main())
