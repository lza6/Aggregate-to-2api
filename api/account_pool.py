"""号池（账号池）：积分制提供商的账号管理 + 自动补号 + 每日签到 + 状态机 (Account FSM)。

覆盖：
- nanobanana-pro（每日签到续额，非用完即丢，每天自动签到）

职责：
- 规范的账号生命周期有限状态机 (Account FSM)：
  unregistered -> registering -> active (ok) -> working -> cooling (exhausted) -> dead (banned)
- 借号 (borrow) / 归还 (release) / 封号标记 (mark_dead) / 冷却标记 (mark_cooling)
- 自动唤醒与延寿巡检器：基于冷却超期或每日重置自动扫描 cooling 账号并恢复/触发签到
- 持久化账号（cookie/邮箱/密码/余额/签到状态/冷却时间/借出时间）到 data/account_pool.db
- 各提供商按需取号（MAB 自适应打分 / 借出互斥）
- 看板：全状态细分统计 (active, working, cooling, dead, registering, total_credits)

P2-3（v7.2.0）：sqlite3 + threading.Lock → aiosqlite + asyncio.Lock，消除事件循环阻塞隐患。
所有 DB 方法改为 async，与 db/core.py 一致（aiosqlite + WAL + busy_timeout）。
旧 to_thread 包装（async_xxx）保留为兼容别名，内部直接 await 原方法（不再丢线程池）。
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import enum
import logging
import os
import random
import sqlite3
import time
from typing import AsyncGenerator

import aiosqlite

from .proxy_pool import proxy_pool
from .providers.base import MOCK_REGISTER

log = logging.getLogger("account_pool")

DB_FILE = os.getenv("IF_ACCOUNT_DB_FILE", "data/account_pool.db")
# nanobanana 目标常驻账号数（默认 500）
TARGET_NANOBANANA = int(os.getenv("IF_NANOBANANA_ACCOUNT_TARGET", "10000"))
# 补号冷却（秒）：注册器连续失败时退避，防风控。
# 7x24h 不间断注册：每成功 1 个后休息 90s（24h ≈ 960 个），
# 既绕开 temp-mail / cf_solver 的 429 限流，又持续累积号池。
REGISTER_COOLDOWN = int(os.getenv("IF_REGISTER_COOLDOWN", "90"))
# 默认账号冷却期（秒）：cooling 状态满此时长后可自动唤醒尝试签到/恢复
DEFAULT_COOLING_PERIOD_SECONDS = float(os.getenv("IF_ACCOUNT_COOLING_PERIOD", "72000"))  # 20 hours
# 借号租约超时（秒）：超过此时长自动重置为 active 防死锁
BORROW_LEASE_TIMEOUT_SECONDS = float(os.getenv("IF_ACCOUNT_BORROW_TIMEOUT", "300"))


class AccountStatus(str, enum.Enum):
    """标准账号生命周期状态枚举。"""

    UNREGISTERED = "unregistered"  # 未注册
    REGISTERING = "registering"  # 注册中
    ACTIVE = "active"  # 就绪可用 (同义词 'ok')
    OK = "ok"  # 兼容历史状态
    WORKING = "working"  # 工作负载中 (被借出)
    COOLING = "cooling"  # 冷却/额度耗尽中 (同义词 'exhausted')
    EXHAUSTED = "exhausted"  # 兼容历史状态
    DEAD = "dead"  # 封号/失效 (同义词 'banned')
    BANNED = "banned"  # 兼容历史状态

    @classmethod
    def canonical(cls, status: str) -> str:
        """标准化状态名称（保持内部一致，向外兼容）。"""
        s = (status or "").strip().lower()
        if s in ("ok", "active"):
            return "active"
        if s in ("exhausted", "cooling"):
            return "cooling"
        if s in ("banned", "dead"):
            return "dead"
        if s == "registering":
            return "registering"
        if s == "working":
            return "working"
        if s == "unregistered":
            return "unregistered"
        return s or "active"


class AdaptiveAccountScore:
    """MAB (Multi-Armed Bandit) 动态评分账号选择器 (基于 EMA 延迟与成功率)。"""

    def __init__(self, email: str):
        self.email = email
        self.ema_latency_ms = 1200.0
        self.success_count = 0
        self.fail_count = 0
        self.consecutive_errors = 0

    def update_result(self, duration_ms: float, is_success: bool):
        alpha = 0.2
        if is_success:
            self.ema_latency_ms = alpha * duration_ms + (1 - alpha) * self.ema_latency_ms
            self.success_count += 1
            self.consecutive_errors = 0
        else:
            self.fail_count += 1
            self.consecutive_errors += 1
            self.ema_latency_ms = max(5000.0, self.ema_latency_ms * 1.5)

    def score(self) -> float:
        total = self.success_count + self.fail_count
        sr = (self.success_count + 1) / (total + 2)  # Laplace 平滑
        latency_score = 1000.0 / max(100.0, self.ema_latency_ms)
        return sr * 50.0 + latency_score * 50.0 - (self.consecutive_errors * 20.0)


class AccountPool:
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

    async def async_borrow_account(
        self, provider: str, prefer_email: str | None = None
    ) -> dict | None:
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

    async def async_mark_dead(
        self, provider: str, email: str, reason: str = "401/403 banned"
    ) -> None:
        """mark_dead 的 async 兼容别名。"""
        await self.mark_dead(provider, email, reason)

    async def async_consume_credits(
        self, provider: str, email: str, amount: int
    ) -> None:
        """consume_credits 的 async 兼容别名。"""
        await self.consume_credits(provider, email, amount)

    async def async_get_adaptive(self, provider: str) -> dict | None:
        """get_adaptive 的 async 兼容别名。"""
        return await self.get_adaptive(provider)

    # ── 状态机核心操作 (FSM, 全 async) ──────────────────────────

    async def _reclaim_lease_timeout(self, provider: str) -> int:
        """回收超租约的 working 账号：超过 BORROW_LEASE_TIMEOUT_SECONDS 自动重置为 active，防止账号永久卡死。"""
        now = time.time()
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(
                "UPDATE accounts SET status='active', borrowed_at=NULL, updated_at=? "
                "WHERE provider=? AND status='working' AND borrowed_at IS NOT NULL AND (?-borrowed_at) > ?",
                (now, provider, now, BORROW_LEASE_TIMEOUT_SECONDS),
            )
            await conn.commit()
            reclaimed = cur.rowcount
        if reclaimed:
            log.info("自动回收超租约 working 账号: %d 个 (%s)", reclaimed, provider)
        return reclaimed

    async def borrow_account(self, provider: str, prefer_email: str | None = None) -> dict | None:
        """从 active (ok) 账号池原子借出一个账号并标记为 working 状态。"""
        now = time.time()
        conn = await self._ensure_conn()
        async with self._lock:
            # 先回收超时残留的 working 账号
            await conn.execute(
                "UPDATE accounts SET status='active', borrowed_at=NULL, updated_at=? "
                "WHERE provider=? AND status='working' AND borrowed_at IS NOT NULL AND (?-borrowed_at) > ?",
                (now, provider, now, BORROW_LEASE_TIMEOUT_SECONDS),
            )

            row = None
            if prefer_email:
                cur = await conn.execute(
                    "SELECT * FROM accounts WHERE provider=? AND email=? AND status IN ('active', 'ok') AND credits > 0",
                    (provider, prefer_email),
                )
                row = await cur.fetchone()

            if not row:
                # 按积分降序及最后更新升序挑选一个
                cur = await conn.execute(
                    "SELECT * FROM accounts WHERE provider=? AND status IN ('active', 'ok') AND credits > 0 "
                    "ORDER BY credits DESC, updated_at ASC LIMIT 1",
                    (provider,),
                )
                row = await cur.fetchone()

            if not row:
                # 如果没有 credits > 0 的，尝试任意 active (ok) 账号（如不需要 credits 的场景）
                cur = await conn.execute(
                    "SELECT * FROM accounts WHERE provider=? AND status IN ('active', 'ok') "
                    "ORDER BY updated_at ASC LIMIT 1",
                    (provider,),
                )
                row = await cur.fetchone()

            if not row:
                return None

            email = row["email"]
            await conn.execute(
                "UPDATE accounts SET status='working', borrowed_at=?, updated_at=? WHERE provider=? AND email=?",
                (now, now, provider, email),
            )
            await conn.commit()

            acc_dict = dict(row)
            acc_dict["status"] = "working"
            acc_dict["borrowed_at"] = now
            return acc_dict

    async def release_account(
        self, provider: str, email: str, new_credits: int | None = None, status: str | None = None, note: str = ""
    ) -> None:
        """请求完毕归还账号：更新积分并根据规则或指定状态转移。"""
        now = time.time()
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT credits, status FROM accounts WHERE provider=? AND email=?", (provider, email)
            )
            cur_row = await cur.fetchone()
            if not cur_row:
                return

            credits_val = new_credits if new_credits is not None else cur_row["credits"]

            # 如果未显式指定目标状态，根据余额和当前状态自动推导
            target_status = status
            cooling_since = None
            if target_status is None:
                if credits_val is not None and credits_val <= 0:
                    target_status = "cooling"
                    cooling_since = now
                else:
                    target_status = "active"

            canonical_status = AccountStatus.canonical(target_status)
            if canonical_status in ("cooling", "exhausted") and cooling_since is None:
                cooling_since = now

            await conn.execute(
                "UPDATE accounts SET credits=?, status=?, note=CASE WHEN ? != '' THEN ? ELSE note END, "
                "cooling_since=COALESCE(?, cooling_since), borrowed_at=NULL, updated_at=? "
                "WHERE provider=? AND email=?",
                (credits_val, target_status, note, note, cooling_since, now, provider, email),
            )
            await conn.commit()

    async def mark_dead(self, provider: str, email: str, reason: str = "401/403 banned") -> None:
        """捕获封号/鉴权失效错误，将账号转移至 dead 状态。"""
        now = time.time()
        conn = await self._ensure_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE accounts SET status='dead', note=?, borrowed_at=NULL, updated_at=? WHERE provider=? AND email=?",
                (reason, now, provider, email),
            )
            await conn.commit()
            log.warning("账号标记封禁 [dead] %s (%s): %s", email, provider, reason)

    async def mark_cooling(self, provider: str, email: str, reason: str = "credits exhausted") -> None:
        """积分耗尽，将账号转移至 cooling 状态并记录冷却开始时间。"""
        now = time.time()
        conn = await self._ensure_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE accounts SET status='cooling', note=?, cooling_since=?, borrowed_at=NULL, updated_at=? "
                "WHERE provider=? AND email=?",
                (reason, now, now, provider, email),
            )
            await conn.commit()
            log.info("账号进入冷却 [cooling] %s (%s): %s", email, provider, reason)

    async def wake_cooling_accounts(
        self, provider: str | None = None, cooling_timeout: float = DEFAULT_COOLING_PERIOD_SECONDS
    ) -> int:
        """扫描 cooling / exhausted 账号，超过冷却时间或每日重置时唤醒恢复为 active。"""
        now = time.time()
        conn = await self._ensure_conn()
        async with self._lock:
            conds = ["status IN ('cooling', 'exhausted')"]
            args: list[object] = []
            if provider:
                conds.append("provider=?")
                args.append(provider)
            # 条件：cooling_since 超时 或 cooling_since 为 NULL
            conds.append("(cooling_since IS NULL OR (? - cooling_since) >= ?)")
            args.extend([now, cooling_timeout])

            where_clause = " WHERE " + " AND ".join(conds)
            cur = await conn.execute(f"SELECT provider, email FROM accounts {where_clause}", args)
            rows = await cur.fetchall()
            if not rows:
                return 0

            for r in rows:
                await conn.execute(
                    "UPDATE accounts SET status='active', cooling_since=NULL, updated_at=? WHERE provider=? AND email=?",
                    (now, r["provider"], r["email"]),
                )
            await conn.commit()
            log.info("自动唤醒冷却账号: %d 个 (%s)", len(rows), provider or "all")
            return len(rows)

    @asynccontextmanager
    async def lease(self, provider: str, prefer_email: str | None = None) -> AsyncGenerator[dict | None, None]:
        """异步上下文管理器：借号并在退出时自动归还/异常处理。

        P2-3 后 borrow/release/mark_dead 均已 async，lease 直接 await 调用。
        """
        acc = await self.borrow_account(provider, prefer_email)
        if not acc:
            yield None
            return
        email = acc["email"]
        try:
            yield acc
        except Exception as e:
            # 如果是 401/403/banned 则 mark_dead，否则正常归还
            err_str = str(e).lower()
            try:
                if any(
                    k in err_str for k in ("401", "403", "unauthorized", "forbidden", "banned", "account suspended")
                ):
                    await self.mark_dead(provider, email, reason=str(e)[:100])
                else:
                    await self.release_account(provider, email)
            except Exception as release_err:
                log.warning("账号归还失败 (%s/%s), 原始异常: %s", provider, email, release_err)
            raise
        else:
            await self.release_account(provider, email)

    # ── 读写兼容接口（全 async）──────────────────────────────

    async def add(
        self,
        provider: str,
        email: str,
        cookie: str,
        password: str | None = None,
        credits: int = 0,
        status: str = "ok",
        note: str = "",
        register_ip: str = "",
    ) -> None:
        now = time.time()
        if cookie == "mock-session":
            note = (note + " mock").strip()
        conn = await self._ensure_conn()
        async with self._lock:
            await conn.execute(
                "INSERT OR REPLACE INTO accounts (provider,email,password,cookie,credits,status,created_at,updated_at,note,cooling_since,borrowed_at,register_ip)"
                " VALUES (?,?,?,?,?,?,?,?,?,NULL,NULL,?)",
                (provider, email, password, cookie, credits, status, now, now, note, register_ip),
            )
            await conn.commit()

    async def list(self, provider: str | None = None, status: str | None = None) -> list[dict]:
        conn = await self._ensure_conn()
        q, args = "SELECT * FROM accounts", []
        conds: list[str] = []
        if provider:
            conds.append("provider=?")
            args.append(provider)
        if status:
            if status in ("ok", "active"):
                conds.append("status IN ('ok', 'active')")
            elif status in ("exhausted", "cooling"):
                conds.append("status IN ('exhausted', 'cooling')")
            elif status in ("banned", "dead"):
                conds.append("status IN ('banned', 'dead')")
            else:
                conds.append("status=?")
                args.append(status)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        async with self._lock:
            cur = await conn.execute(q + " ORDER BY created_at DESC", args)
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_page(
        self,
        provider: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
        search: str = "",
    ) -> dict:
        """分页读取账号列表，避免百万级号池一次性加载到内存。"""
        page = max(1, int(page))
        page_size = min(100, max(1, int(page_size)))
        conds: list[str] = []
        args: list[object] = []
        if provider:
            conds.append("provider=?")
            args.append(provider)
        if status:
            if status in ("ok", "active"):
                conds.append("status IN ('ok', 'active')")
            elif status in ("exhausted", "cooling"):
                conds.append("status IN ('exhausted', 'cooling')")
            elif status in ("banned", "dead"):
                conds.append("status IN ('banned', 'dead')")
            else:
                conds.append("status=?")
                args.append(status)
        if search:
            conds.append("(email LIKE ? OR status LIKE ? OR register_ip LIKE ?)")
            needle = f"%{search.strip()}%"
            args.extend([needle, needle, needle])
        where = f" WHERE {' AND '.join(conds)}" if conds else ""
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(f"SELECT COUNT(*) FROM accounts{where}", args)
            total_row = await cur.fetchone()
            total = total_row[0] if total_row else 0
            offset = (page - 1) * page_size
            cur = await conn.execute(
                f"SELECT * FROM accounts{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*args, page_size, offset],
            )
            rows = await cur.fetchall()
        return {
            "items": [dict(r) for r in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (int(total) + page_size - 1) // page_size),
        }

    async def get(self, provider: str) -> list[dict]:
        """某提供商当前就绪可用账号（含 cookie，供 Provider 用）。"""
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT * FROM accounts WHERE provider=? AND status IN ('ok', 'active') ORDER BY created_at DESC",
                (provider,),
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def update_credits(self, provider: str, email: str, credits: int) -> None:
        conn = await self._ensure_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE accounts SET credits=?, updated_at=? WHERE provider=? AND email=?",
                (credits, time.time(), provider, email),
            )
            await conn.commit()

    async def consume_credits(self, provider: str, email: str, amount: int) -> None:
        """v6.5.1: 生成成功扣减该账号积分，并累计「消耗积分」画像（images_used / credits_used_total）。

        - credits：剩余可用积分（扣减后，下限 0）
        - credits_used_total：该账号累计消耗积分（自增 amount）
        - images_used：该账号累计出图次数（自增 1）
        - last_used_at：最近一次出图时间
        """
        if amount <= 0:
            return
        conn = await self._ensure_conn()
        now = time.time()
        async with self._lock:
            await conn.execute(
                "UPDATE accounts SET credits=MAX(0, credits-?),"
                " credits_used_total=COALESCE(credits_used_total,0)+?,"
                " images_used=COALESCE(images_used,0)+1,"
                " last_used_at=?, updated_at=?"
                " WHERE provider=? AND email=?",
                (amount, amount, now, now, provider, email),
            )
            await conn.commit()

    async def mark(self, provider: str, email: str, status: str, note: str = "") -> None:
        now = time.time()
        cooling_since = now if status in ("cooling", "exhausted") else None
        conn = await self._ensure_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE accounts SET status=?, note=?, cooling_since=?, updated_at=? WHERE provider=? AND email=?",
                (status, note, cooling_since, now, provider, email),
            )
            await conn.commit()

    async def set_checkin(self, provider: str, email: str, checkin_at: float) -> None:
        conn = await self._ensure_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE accounts SET checkin_at=? WHERE provider=? AND email=?", (checkin_at, provider, email)
            )
            await conn.commit()

    async def set_checkin_profile(
        self,
        provider: str,
        email: str,
        checkin_at: float,
        cycle_day: int = 0,
        reward: int = 0,
        next_claim_at: float | None = None,
    ) -> None:
        """v6.3.4: 签到成功后一次性落库完整画像。

        - checkin_at：本次签到时间戳
        - checkin_cycle_day：上游 claim 响应的 cycleDay（7 天周期内第几天）
        - checkin_total：累计签到天数（自增 1）
        - credits_earned_total：累计获得积分（累计 reward）
        - next_claim_at：上游 nextClaimAt（美区时区重置点）
        """
        conn = await self._ensure_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE accounts SET checkin_at=?, checkin_cycle_day=?,"
                " checkin_total=COALESCE(checkin_total,0)+1,"
                " credits_earned_total=COALESCE(credits_earned_total,0)+?,"
                " next_claim_at=?, updated_at=?"
                " WHERE provider=? AND email=?",
                (checkin_at, int(cycle_day or 0), int(reward or 0), next_claim_at, time.time(), provider, email),
            )
            await conn.commit()

    async def counts(self) -> dict:
        """返回全状态细分统计 (映射为标准 key 与历史 key 兼容)。"""
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT provider, status, COUNT(*) c FROM accounts GROUP BY provider, status"
            )
            rows = await cur.fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            p = r["provider"]
            st = r["status"]
            cnt = r["c"]
            prov_dict = out.setdefault(
                p,
                {
                    "active": 0,
                    "ok": 0,
                    "working": 0,
                    "cooling": 0,
                    "exhausted": 0,
                    "dead": 0,
                    "banned": 0,
                    "registering": 0,
                    "unregistered": 0,
                },
            )
            prov_dict[st] = prov_dict.get(st, 0) + cnt
            # 状态别名同步累加
            if st in ("ok", "active"):
                prov_dict["active"] += cnt if st != "active" else 0
                prov_dict["ok"] += cnt if st != "ok" else 0
            elif st in ("cooling", "exhausted"):
                prov_dict["cooling"] += cnt if st != "cooling" else 0
                prov_dict["exhausted"] += cnt if st != "exhausted" else 0
            elif st in ("dead", "banned"):
                prov_dict["dead"] += cnt if st != "dead" else 0
                prov_dict["banned"] += cnt if st != "banned" else 0
        return out

    async def total_credits(self, provider: str) -> int:
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT COALESCE(SUM(credits),0) s FROM accounts WHERE provider=? AND status IN ('ok', 'active', 'working')",
                (provider,),
            )
            r = await cur.fetchone()
        return int(r["s"]) if r else 0

    async def cost_summary(self, provider: str) -> dict:
        """成本口径聚合（配合 P1-3「成本口径」主卡）。

        - total_credits_used：全部账号累计消耗积分（v6.5.1 起扣减累计）
        - total_images_used：累计出图次数
        - total_credits_earned：累计获得积分（签到）
        - avg_cost_per_image：平均每张成本 = 累计消耗 / 出图次数（无出图时 None）
        - accounts_with_usage / total_accounts：有消耗账号数与总数（口径覆盖率）
        """
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT COALESCE(SUM(credits_used_total),0) c_used,"
                " COALESCE(SUM(images_used),0) imgs,"
                " COALESCE(SUM(credits_earned_total),0) c_earned,"
                " COUNT(CASE WHEN COALESCE(images_used,0) > 0 THEN 1 END) used_accs,"
                " COUNT(*) total_accs"
                " FROM accounts WHERE provider=?",
                (provider,),
            )
            row = await cur.fetchone()
        c_used = int(row["c_used"] or 0)
        imgs = int(row["imgs"] or 0)
        return {
            "total_credits_used": c_used,
            "total_images_used": imgs,
            "total_credits_earned": int(row["c_earned"] or 0),
            "accounts_with_usage": int(row["used_accs"] or 0),
            "total_accounts": int(row["total_accs"] or 0),
            "avg_cost_per_image": round(c_used / imgs, 1) if imgs > 0 else None,
        }

    # ── 补号速率画像 (P3-4) ──────────────────────────────
    async def growth_stats(self, provider: str) -> dict:
        """号池补满速率画像：「每天新增账号数」+「距目标还需几天」。

        - new_in_24h: 最近 24h 新注册账号数（≈ 每日新增速率缓存）
        - new_in_7d / avg_daily_7d: 7 天新增 / 日均（平滑短窗抖动）
        - gap: 距目标还差的可用(ok/active)账号数
        - eta_days: 预计达标天数 = gap / 每日速率；速率为 0 时 None（无法估算）
        """
        now = time.time()
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute("SELECT COUNT(*) FROM accounts WHERE provider=?", (provider,))
            total = (await cur.fetchone())[0]
            cur = await conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE provider=? AND created_at >= ?",
                (provider, now - 86400),
            )
            new_in_24h = (await cur.fetchone())[0]
            cur = await conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE provider=? AND created_at >= ?",
                (provider, now - 7 * 86400),
            )
            new_in_7d = (await cur.fetchone())[0]
        ok = len(await self.get(provider))
        target = TARGET_NANOBANANA
        daily_rate = float(new_in_24h)
        gap = max(0, target - ok)
        eta_days = round(gap / daily_rate, 1) if daily_rate > 0 else None
        return {
            "total": int(total),
            "new_in_24h": int(new_in_24h),
            "new_in_7d": int(new_in_7d),
            "avg_daily_7d": round(new_in_7d / 7.0, 1),
            "ok": ok,
            "target": int(target),
            "gap": int(gap),
            "eta_days": eta_days,
        }

    # ── 自动补号 / 签到 / 延寿唤醒循环 ────────────────────────
    async def start(self) -> None:
        # 为长效签到型提供商（nanobanana）开启自动补号与延寿巡检
        auto_provs = [p for p in ("nanobanana",) if self._autoreg_enabled(p)]
        for prov in auto_provs:
            self.checkin_tasks[f"register:{prov}"] = asyncio.create_task(self._autoregister_loop(prov))
        # 每日签到与自动延寿巡检器
        self.checkin_tasks["nanobanana_checkin"] = asyncio.create_task(self._daily_checkin_loop("nanobanana"))
        self.checkin_tasks["wake_inspector"] = asyncio.create_task(self._cooling_wake_loop())
        log.info("号池 FSM 引擎启动：自动补号 %s + 签到与延寿唤醒巡检器就绪", auto_provs)

    @staticmethod
    def _autoreg_enabled(provider: str) -> bool:
        return os.getenv("IF_NANOBANANA_AUTOREG", "1").strip().lower() in {"1", "true", "yes", "on"}

    async def stop(self) -> None:
        for t in self.checkin_tasks.values():
            t.cancel()
        if self.checkin_tasks:
            await asyncio.gather(*self.checkin_tasks.values(), return_exceptions=True)
        self.checkin_tasks.clear()
        await self._close_conn_safe()

    async def _cooling_wake_loop(self) -> None:
        """延寿唤醒巡检：每 5 分钟先回收超租约 working 账号，再扫描冷却账号并自动唤醒恢复。"""
        while True:
            try:
                await asyncio.sleep(300)
                for prov in ("nanobanana",):
                    # P2-3: 方法已 async，直接 await（不再 to_thread）
                    await self._reclaim_lease_timeout(prov)
                    await self.wake_cooling_accounts(prov)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("延寿唤醒巡检器异常: %s", e)

    async def _autoregister_loop(self, provider: str) -> None:
        """提供商自动补号守护任务。"""
        target = TARGET_NANOBANANA
        while True:
            try:
                usable = len(await self.get(provider))
                if usable >= target:
                    await asyncio.sleep(60)
                    continue
                reg = self.registerers.get(provider)
                if reg is None:
                    await asyncio.sleep(30)
                    continue

                try:
                    if not MOCK_REGISTER:
                        # 号池注册需轮换 IP：只要池里有任何代理就尝试 acquire（内部按冷却分配）。
                        # 不能用 available()（受 IF_PROXY_MAX_USE_PER_DAY=1 每日限额约束）做前置判定，
                        # 否则用一轮后全部 use_count=1 会被误判"无可用代理"而永久暂停。
                        if not proxy_pool.entries:
                            log.info("号池补号暂停 %s：代理池为空（抓取器尚未注入）", provider)
                            await asyncio.sleep(REGISTER_COOLDOWN)
                            continue
                    reg.proxy = await proxy_pool.acquire()
                    acc = await reg.register_one()
                    if acc:
                        await self.add(
                            provider,
                            acc["email"],
                            acc["cookie"],
                            acc.get("password"),
                            credits=acc.get("credits", 0),
                            register_ip=acc.get("register_ip", ""),
                        )
                        await self.mark(provider, acc["email"], "ok")
                        log.info("号池补号成功 %s: %s（现有 %d）", provider, acc["email"], len(await self.get(provider)))
                        await asyncio.sleep(REGISTER_COOLDOWN)
                    else:
                        await asyncio.sleep(REGISTER_COOLDOWN)
                except Exception as e:
                    log.warning("号池补号失败 %s: %s", provider, e)
                    await asyncio.sleep(REGISTER_COOLDOWN)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("号池补号循环异常 %s: %s", provider, e)
                await asyncio.sleep(30)

    async def _load_checkin_batch(self, provider: str, cutoff: float, size: int) -> list[dict]:
        """SQL 层过滤签到账号（async + 锁保护），供 _daily_checkin_loop 调用。

        P2-3: 已 async，直接在事件循环线程跑（aiosqlite 内部线程池处理 I/O，不阻塞 loop）。
        """
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT * FROM accounts WHERE provider=? AND status IN ('ok', 'active') "
                "AND (checkin_at IS NULL OR checkin_at < ?) ORDER BY checkin_at ASC LIMIT ?",
                (provider, cutoff, size),
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def _daily_checkin_loop(self, provider: str) -> None:
        """nanobanana：定时检查签到（按时区与间隔），按批次处理避免 O(n)。"""
        BATCH_SIZE = 500  # 每轮最多处理 500 个账号，避免单次全表扫描阻塞事件循环
        first_cycle = True
        while True:
            try:
                # 启动后先等 60s，让 provider/代理池完成初始化；随后每 30 分钟巡检。
                await asyncio.sleep(60 if first_cycle else 1800)
                first_cycle = False
                reg = self.registerers.get(provider)
                if reg is None:
                    continue
                now = time.time()
                cutoff = now - 20 * 3600  # 距上次签到 >20h → 补签
                # P2-3: _load_checkin_batch 已 async，直接 await（不再 to_thread）
                rows = await self._load_checkin_batch(provider, cutoff, BATCH_SIZE)
                if not rows:
                    continue
                for row in rows:
                    acc = dict(row)
                    try:
                        ok = await reg.checkin(acc)
                        if ok:
                            # v6.3.4: checkin 现返回 {credits, reward?, cycle_day?, next_claim_at?} 画像 dict
                            # 兼容旧的 int 返回（仅余额）
                            if isinstance(ok, dict):
                                credits = int(ok.get("credits") or 0)
                                await self.set_checkin_profile(
                                    provider,
                                    acc["email"],
                                    time.time(),
                                    cycle_day=int(ok.get("cycle_day") or 0),
                                    reward=int(ok.get("reward") or 0),
                                    next_claim_at=ok.get("next_claim_at"),
                                )
                            else:
                                credits = int(ok or 0)
                                await self.set_checkin(provider, acc["email"], time.time())
                            if credits:
                                await self.update_credits(provider, acc["email"], credits)
                            await self.mark(provider, acc["email"], "active")
                            continue
                        # checkin 返回 None（cookie 失效）→ 尝试用保存的密码重新登录续期
                        # 注意：checkin 失败不一定是 cookie 过期（也可能是网络/求解临时故障），
                        # 用连续失败计数（note 里的 fail:N 标记）代替一次就标 dead。
                        if acc.get("password") and hasattr(reg, "re_login"):
                            re = await reg.re_login(acc["email"], acc["password"])
                            if re and re.get("cookie"):
                                await self.add(
                                    provider,
                                    acc["email"],
                                    re["cookie"],
                                    password=acc.get("password"),
                                    credits=int(acc.get("credits") or 0),
                                    status="active",
                                    note=acc.get("note") or "",
                                    register_ip=acc.get("register_ip") or "",
                                )
                                log.info("nanobanana cookie 续期成功 %s", acc["email"])
                            else:
                                # 累计失败计数，>=3 次才标 dead
                                prev_note = acc.get("note") or ""
                                fail_n = int(prev_note.split("fail:")[1]) if "fail:" in prev_note else 1
                                if fail_n >= 3:
                                    await self.mark(provider, acc["email"], "dead", note=f"cookie 续期连续 {fail_n} 次失败")
                                else:
                                    await self.mark(provider, acc["email"], "active", note=f"fail:{fail_n + 1}")
                                    log.warning("nanobanana %s checkin+re_login 失败 (第 %d 次)", acc["email"], fail_n)
                        else:
                            await self.mark(provider, acc["email"], "dead", note="cookie 失效（无密码可续期）")
                    except Exception as e:
                        log.warning("nanobanana 签到失败 %s: %s", acc["email"], e)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("签到循环异常 %s: %s", provider, e)

    async def dashboard(self) -> dict:
        """前端「号池」看板数据：包含 nanobanana 等所有受支持提供商。"""
        counts = await self.counts()
        out = {}
        all_providers = set(counts.keys()) | {"nanobanana"}
        for prov in all_providers:
            c = counts.get(prov, {})
            # 兼容读取各状态计数
            ok_cnt = c.get("ok", 0) or c.get("active", 0)
            working_cnt = c.get("working", 0)
            exhausted_cnt = c.get("exhausted", 0) or c.get("cooling", 0)
            dead_cnt = c.get("dead", 0) or c.get("banned", 0)
            registering_cnt = c.get("registering", 0)
            unregistered_cnt = c.get("unregistered", 0)

            target = TARGET_NANOBANANA
            # 总数按原始各状态去重汇总
            raw_total = sum(v for k, v in c.items() if k not in ("active", "cooling", "dead"))
            if raw_total == 0:
                raw_total = ok_cnt + working_cnt + exhausted_cnt + dead_cnt + registering_cnt + unregistered_cnt

            out[prov] = {
                "total": raw_total,
                "ok": ok_cnt,
                "active": ok_cnt,
                "working": working_cnt,
                "exhausted": exhausted_cnt,
                "cooling": exhausted_cnt,
                "dead": dead_cnt,
                "banned": dead_cnt,
                "registering": registering_cnt,
                "unregistered": unregistered_cnt,
                "credits": await self.total_credits(prov),
                "target": target,
                "auto_register": self.registerers.get(prov) is not None,
            }
        return out


# 模块级单例
account_pool = AccountPool()
