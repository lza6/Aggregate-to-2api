"""AccountPool 基类：连接生命周期 + MAB 评分 + async 兼容包装（P0-F2 拆分）。

连接管理（_ensure_conn/_close_conn_safe/_init_schema）与 MAB 评分
（get_adaptive/_get_or_create_score/report_result）以及旧 async_xxx 兼容
别名集中于此；FSM 借还/签到/看板/CRUD/巡检逻辑在各 mixin 子模块。

向后兼容：`AccountPool` 在 pool.py 多继承各 mixin + 本基类组合而成，
所有公共方法签名/返回结构不变。
"""

from __future__ import annotations

import asyncio
import logging
import random
import sqlite3

import aiosqlite

from ._constants import DB_FILE
from .scoring import AdaptiveAccountScore

log = logging.getLogger("account_pool")


class AccountPoolBase:
    """P2-3: aiosqlite + asyncio.Lock 全 async 实现，与 db/core.py 一致。

    原同步 sqlite3 + threading.Lock 在 async 路径（nanobanana.generate / registerer）
    直接阻塞事件循环；现全部 async 化，连接在 _get_conn 惰性创建（同 loop 复用）。
    """

    def __init__(self, db_path: str = DB_FILE) -> None:
        self._db_path = db_path
        # aiosqlite 连接惰性初始化（需在运行 loop 内创建，避免跨 loop）
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._initialized = False
        self._pool_loop: asyncio.AbstractEventLoop | None = None
        # 注册器/签到器注入（避免循环 import）
        self.registerers: dict[str, object] = {}
        self.checkin_tasks: dict[str, asyncio.Task] = {}
        self._scores: dict[str, AdaptiveAccountScore] = {}
        # 看板状态
        self.stats: dict[str, dict] = {}
        # P1-7 FSM 自愈：cooling 账号签到恢复连续失败计数（内存态，不改 DB schema）
        self._selfheal_retry: dict[tuple[str, str], int] = {}

    async def _ensure_conn(self) -> aiosqlite.Connection | None:
        """惰性创建/复用 aiosqlite 连接，绑定当前 loop（跨 loop 重建）。

        异常安全（P3 审计修复）：connect 或 PRAGMA 失败（如损坏 DB）时 close 本地连接
        并重置状态，避免非 daemon 线程泄漏 / 后续并发 connect 挂起；调用方（get 等）
        在异常时可优雅降级为空结果，而非穿透 500。
        """
        cur_loop = asyncio.get_running_loop()
        if self._conn is not None and self._pool_loop is cur_loop and not self._conn._connection:
            # 连接已关闭，重建
            self._conn = None
            self._initialized = False
        if self._conn is None or self._pool_loop is not cur_loop:
            if self._pool_loop is not None and self._pool_loop is not cur_loop:
                # loop 漂移：关旧连接
                await self._close_conn_safe()
            conn = None
            try:
                conn = await aiosqlite.connect(self._db_path, timeout=10, isolation_level=None)
                conn.row_factory = aiosqlite.Row
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("PRAGMA busy_timeout=10000")
                await conn.execute("PRAGMA cache_size=-64000")  # 64MB
                await conn.execute("PRAGMA mmap_size=268435456")  # 256MB
                await conn.execute("PRAGMA temp_store=MEMORY")
                self._conn = conn
                self._pool_loop = cur_loop
                if not self._initialized:
                    await self._init_schema(conn)
                    self._initialized = True
            except sqlite3.DatabaseError as e:
                # 损坏 DB 或 schema 建失败：关闭连接防泄漏，重置状态，降级重抛
                log.warning("account_pool 打开 DB 失败（可能损坏）: %s", e)
                if conn is not None:
                    try:
                        await conn.close()
                    except Exception:
                        pass
                self._conn = None
                self._pool_loop = None
                self._initialized = False
                raise
            except Exception as e:
                # 其余异常（权限/IO）同样关闭连接防泄漏
                log.warning("account_pool 连接初始化异常: %s", e)
                if conn is not None:
                    try:
                        await conn.close()
                    except Exception:
                        pass
                self._conn = None
                self._pool_loop = None
                self._initialized = False
                raise
        return self._conn

    async def _close_conn_safe(self) -> None:
        """安全关闭旧连接（loop 已死或漂移时）。"""
        if self._conn is None:
            return
        try:
            await self._conn.close()
        except Exception:
            pass
        self._conn = None
        self._initialized = False

    async def _init_schema(self, conn: aiosqlite.Connection) -> None:
        """初始化表 + 向下兼容迁移（aiosqlite async）。"""
        async with self._lock:
            await conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                provider      TEXT NOT NULL,
                email         TEXT NOT NULL,
                password      TEXT,
                cookie        TEXT,
                credits       INTEGER DEFAULT 0,
                status        TEXT DEFAULT 'ok',       -- ok/active | working | cooling/exhausted | dead/banned | registering | unregistered
                checkin_at    REAL,                     -- nanobanana 上次签到时间
                created_at    REAL,
                updated_at    REAL,
                cooling_since REAL,                     -- 进入 cooling 状态的时间戳
                borrowed_at   REAL,                     -- 借出为 working 的时间戳
                register_ip   TEXT,
                note          TEXT,
                PRIMARY KEY (provider, email)
            );
            CREATE INDEX IF NOT EXISTS idx_acc_provider_status ON accounts(provider, status);
            """)
            # 向下兼容：如果已有旧表缺少列则自动升级
            try:
                cur = await conn.execute("PRAGMA table_info(accounts)")
                cols = [r["name"] async for r in cur]
                if "cooling_since" not in cols:
                    await conn.execute("ALTER TABLE accounts ADD COLUMN cooling_since REAL")
                if "borrowed_at" not in cols:
                    await conn.execute("ALTER TABLE accounts ADD COLUMN borrowed_at REAL")
                if "register_ip" not in cols:
                    await conn.execute("ALTER TABLE accounts ADD COLUMN register_ip TEXT")
                # v6.3.4: 签到周期画像（上游 claim 响应的 cycleDay/rewardAmount 落库）
                if "checkin_cycle_day" not in cols:
                    await conn.execute("ALTER TABLE accounts ADD COLUMN checkin_cycle_day INTEGER DEFAULT 0")
                if "checkin_total" not in cols:
                    await conn.execute("ALTER TABLE accounts ADD COLUMN checkin_total INTEGER DEFAULT 0")
                if "credits_earned_total" not in cols:
                    await conn.execute("ALTER TABLE accounts ADD COLUMN credits_earned_total INTEGER DEFAULT 0")
                if "next_claim_at" not in cols:
                    await conn.execute("ALTER TABLE accounts ADD COLUMN next_claim_at REAL")
                # v6.5.1: 每账号出图消耗画像（生成成功扣减 + 累计消耗积分/出图次数/最近出图时间）
                if "credits_used_total" not in cols:
                    await conn.execute("ALTER TABLE accounts ADD COLUMN credits_used_total INTEGER DEFAULT 0")
                if "images_used" not in cols:
                    await conn.execute("ALTER TABLE accounts ADD COLUMN images_used INTEGER DEFAULT 0")
                if "last_used_at" not in cols:
                    await conn.execute("ALTER TABLE accounts ADD COLUMN last_used_at REAL")
            except Exception as e:
                log.debug("Schema migration check: %s", e)
            await conn.commit()

    async def get_adaptive(self, provider: str) -> dict | None:
        """基于 Epsilon-Greedy MAB 动态评分返回综合最优可用账号。"""
        accs = await self.get(provider)
        if not accs:
            return None
        # 10% 概率探索
        if random.random() < 0.1:
            return random.choice(accs)
        # 90% 概率选择最高分账号
        best_acc = max(accs, key=lambda a: self._get_or_create_score(a["email"]).score())
        return best_acc

    def _get_or_create_score(self, email: str) -> AdaptiveAccountScore:
        if email not in self._scores:
            self._scores[email] = AdaptiveAccountScore(email)
        return self._scores[email]

    def report_result(self, email: str, duration_ms: float, is_success: bool) -> None:
        sc = self._get_or_create_score(email)
        sc.update_result(duration_ms, is_success)

    # ── 兼容包装（旧 async_xxx = to_thread(self.sync_xxx)）──────────
    # P2-3 迁移后原方法已 async，这些包装保留为别名（内部直接 await，不再丢线程池），
    # 保证旧调用方 account_pool.async_get / async_consume_credits 等零改动可用。
    async def async_get(self, provider: str) -> list[dict]:
        """get 的 async 兼容别名（P2-3 后原方法已 async，直接 await）。"""
        return await self.get(provider)

    async def async_borrow_account(self, provider: str, prefer_email: str | None = None) -> dict | None:
        """borrow_account 的 async 兼容别名。"""
        return await self.borrow_account(provider, prefer_email)

    async def async_release_account(
        self,
        provider: str,
        email: str,
        new_credits: int | None = None,
        status: str | None = None,
        note: str = "",
    ) -> None:
        """release_account 的 async 兼容别名。"""
        await self.release_account(provider, email, new_credits, status, note)

    async def async_mark_dead(self, provider: str, email: str, reason: str = "401/403 banned") -> None:
        """mark_dead 的 async 兼容别名。"""
        await self.mark_dead(provider, email, reason)

    async def async_consume_credits(self, provider: str, email: str, amount: int) -> None:
        """consume_credits 的 async 兼容别名。"""
        await self.consume_credits(provider, email, amount)

    async def async_get_adaptive(self, provider: str) -> dict | None:
        """get_adaptive 的 async 兼容别名。"""
        return await self.get_adaptive(provider)
