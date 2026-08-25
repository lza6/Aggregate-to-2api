"""号池（账号池）：积分制提供商的账号管理 + 自动补号 + 每日签到 + 状态机 (Account FSM)。

覆盖：
- minimaxh3（用完即丢，自动注册补号，目标常驻 500 个）
- nanobanana-pro（每日签到续额，非用完即丢，每天自动签到）

职责：
- 规范的账号生命周期有限状态机 (Account FSM)：
  unregistered -> registering -> active (ok) -> working -> cooling (exhausted) -> dead (banned)
- 借号 (borrow) / 归还 (release) / 封号标记 (mark_dead) / 冷却标记 (mark_cooling)
- 自动唤醒与延寿巡检器：基于冷却超期或每日重置自动扫描 cooling 账号并恢复/触发签到
- 持久化账号（cookie/邮箱/密码/余额/签到状态/冷却时间/借出时间）到 data/account_pool.db
- 各提供商按需取号（MAB 自适应打分 / 借出互斥）
- 看板：全状态细分统计 (active, working, cooling, dead, registering, total_credits)
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import enum
import logging
import os
import sqlite3
import threading
import time
from typing import AsyncGenerator

from .proxy_pool import proxy_pool
from .providers.base import MOCK_REGISTER

log = logging.getLogger("account_pool")

DB_FILE = os.getenv("IF_ACCOUNT_DB_FILE", "data/account_pool.db")
# minimaxh3 目标常驻账号数（默认 500）
TARGET_MINIMAXH3 = int(os.getenv("IF_MINIMAXH3_ACCOUNT_TARGET", "500"))
# nanobanana 目标常驻账号数（默认 500）
TARGET_NANOBANANA = int(os.getenv("IF_NANOBANANA_ACCOUNT_TARGET", "500"))
# 补号冷却（秒）：注册器连续失败时退避，防风控
REGISTER_COOLDOWN = int(os.getenv("IF_REGISTER_COOLDOWN", "120"))
# 默认账号冷却期（秒）：cooling 状态满此时长后可自动唤醒尝试签到/恢复
DEFAULT_COOLING_PERIOD_SECONDS = float(os.getenv("IF_ACCOUNT_COOLING_PERIOD", "72000"))  # 20 hours
# 借号租约超时（秒）：超过此时长自动重置为 active 防死锁
BORROW_LEASE_TIMEOUT_SECONDS = float(os.getenv("IF_ACCOUNT_BORROW_TIMEOUT", "300"))


class AccountStatus(str, enum.Enum):
    """标准账号生命周期状态枚举。"""
    UNREGISTERED = "unregistered"  # 未注册
    REGISTERING = "registering"    # 注册中
    ACTIVE = "active"              # 就绪可用 (同义词 'ok')
    OK = "ok"                      # 兼容历史状态
    WORKING = "working"            # 工作负载中 (被借出)
    COOLING = "cooling"            # 冷却/额度耗尽中 (同义词 'exhausted')
    EXHAUSTED = "exhausted"        # 兼容历史状态
    DEAD = "dead"                  # 封号/失效 (同义词 'banned')
    BANNED = "banned"              # 兼容历史状态

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
    def __init__(self, db_path: str = DB_FILE) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()
        # 注册器/签到器注入（避免循环 import）
        self.registerers: dict[str, object] = {}
        self.checkin_tasks: dict[str, asyncio.Task] = {}
        self._scores: dict[str, AdaptiveAccountScore] = {}
        # 看板状态
        self.stats: dict[str, dict] = {}

    def get_adaptive(self, provider: str) -> dict | None:
        """基于 Epsilon-Greedy MAB 动态评分返回综合最优可用账号。"""
        accs = self.get(provider)
        if not accs:
            return None
        import random
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

    def _init_schema(self) -> None:
        with self._lock:
            # 基础表
            self._conn.executescript("""
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
                note          TEXT,
                PRIMARY KEY (provider, email)
            );
            CREATE INDEX IF NOT EXISTS idx_acc_provider_status ON accounts(provider, status);
            """)
            # 向下兼容：如果已有旧表缺少 cooling_since / borrowed_at 列则自动升级
            try:
                cols = [r["name"] for r in self._conn.execute("PRAGMA table_info(accounts)").fetchall()]
                if "cooling_since" not in cols:
                    self._conn.execute("ALTER TABLE accounts ADD COLUMN cooling_since REAL")
                if "borrowed_at" not in cols:
                    self._conn.execute("ALTER TABLE accounts ADD COLUMN borrowed_at REAL")
            except Exception as e:
                log.debug("Schema migration check: %s", e)
            self._conn.commit()

    # ── 状态机核心操作 (FSM) ──────────────────────────

    def borrow_account(self, provider: str, prefer_email: str | None = None) -> dict | None:
        """从 active (ok) 账号池原子借出一个账号并标记为 working 状态。"""
        now = time.time()
        with self._lock:
            # 先回收超时残留的 working 账号
            self._conn.execute(
                "UPDATE accounts SET status='active', borrowed_at=NULL, updated_at=? "
                "WHERE provider=? AND status='working' AND borrowed_at IS NOT NULL AND (?-borrowed_at) > ?",
                (now, provider, now, BORROW_LEASE_TIMEOUT_SECONDS)
            )

            row = None
            if prefer_email:
                row = self._conn.execute(
                    "SELECT * FROM accounts WHERE provider=? AND email=? AND status IN ('active', 'ok') AND credits > 0",
                    (provider, prefer_email)
                ).fetchone()

            if not row:
                # 按积分降序及最后更新升序挑选一个
                row = self._conn.execute(
                    "SELECT * FROM accounts WHERE provider=? AND status IN ('active', 'ok') AND credits > 0 "
                    "ORDER BY credits DESC, updated_at ASC LIMIT 1",
                    (provider,)
                ).fetchone()

            if not row:
                # 如果没有 credits > 0 的，尝试任意 active (ok) 账号（如不需要 credits 的场景）
                row = self._conn.execute(
                    "SELECT * FROM accounts WHERE provider=? AND status IN ('active', 'ok') "
                    "ORDER BY updated_at ASC LIMIT 1",
                    (provider,)
                ).fetchone()

            if not row:
                return None

            email = row["email"]
            self._conn.execute(
                "UPDATE accounts SET status='working', borrowed_at=?, updated_at=? WHERE provider=? AND email=?",
                (now, now, provider, email)
            )
            self._conn.commit()

            acc_dict = dict(row)
            acc_dict["status"] = "working"
            acc_dict["borrowed_at"] = now
            return acc_dict

    def release_account(self, provider: str, email: str, new_credits: int | None = None,
                        status: str | None = None, note: str = "") -> None:
        """请求完毕归还账号：更新积分并根据规则或指定状态转移。"""
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                "SELECT credits, status FROM accounts WHERE provider=? AND email=?",
                (provider, email)
            ).fetchone()
            if not cur:
                return

            credits_val = new_credits if new_credits is not None else cur["credits"]

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

            self._conn.execute(
                "UPDATE accounts SET credits=?, status=?, note=CASE WHEN ? != '' THEN ? ELSE note END, "
                "cooling_since=COALESCE(?, cooling_since), borrowed_at=NULL, updated_at=? "
                "WHERE provider=? AND email=?",
                (credits_val, target_status, note, note, cooling_since, now, provider, email)
            )
            self._conn.commit()

    def mark_dead(self, provider: str, email: str, reason: str = "401/403 banned") -> None:
        """捕获封号/鉴权失效错误，将账号转移至 dead 状态。"""
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE accounts SET status='dead', note=?, borrowed_at=NULL, updated_at=? WHERE provider=? AND email=?",
                (reason, now, provider, email)
            )
            self._conn.commit()
            log.warning("账号标记封禁 [dead] %s (%s): %s", email, provider, reason)

    def mark_cooling(self, provider: str, email: str, reason: str = "credits exhausted") -> None:
        """积分耗尽，将账号转移至 cooling 状态并记录冷却开始时间。"""
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE accounts SET status='cooling', note=?, cooling_since=?, borrowed_at=NULL, updated_at=? "
                "WHERE provider=? AND email=?",
                (reason, now, now, provider, email)
            )
            self._conn.commit()
            log.info("账号进入冷却 [cooling] %s (%s): %s", email, provider, reason)

    def wake_cooling_accounts(self, provider: str | None = None, cooling_timeout: float = DEFAULT_COOLING_PERIOD_SECONDS) -> int:
        """扫描 cooling / exhausted 账号，超过冷却时间或每日重置时唤醒恢复为 active。"""
        now = time.time()
        with self._lock:
            conds = ["status IN ('cooling', 'exhausted')"]
            args = []
            if provider:
                conds.append("provider=?")
                args.append(provider)
            # 条件：cooling_since 超时 或 cooling_since 为 NULL
            conds.append(f"(cooling_since IS NULL OR (? - cooling_since) >= ?)")
            args.extend([now, cooling_timeout])

            where_clause = " WHERE " + " AND ".join(conds)
            rows = self._conn.execute(f"SELECT provider, email FROM accounts {where_clause}", args).fetchall()
            if not rows:
                return 0

            for r in rows:
                self._conn.execute(
                    "UPDATE accounts SET status='active', cooling_since=NULL, updated_at=? WHERE provider=? AND email=?",
                    (now, r["provider"], r["email"])
                )
            self._conn.commit()
            log.info("自动唤醒冷却账号: %d 个 (%s)", len(rows), provider or "all")
            return len(rows)

    @asynccontextmanager
    async def lease(self, provider: str, prefer_email: str | None = None) -> AsyncGenerator[dict | None, None]:
        """异步上下文管理器：借号并在退出时自动归还/异常处理。"""
        acc = self.borrow_account(provider, prefer_email)
        if not acc:
            yield None
            return
        email = acc["email"]
        try:
            yield acc
        except Exception as e:
            # 如果是 401/403/banned 则 mark_dead，否则正常归还
            err_str = str(e).lower()
            if any(k in err_str for k in ("401", "403", "unauthorized", "forbidden", "banned", "account suspended")):
                self.mark_dead(provider, email, reason=str(e)[:100])
            else:
                self.release_account(provider, email)
            raise
        else:
            self.release_account(provider, email)

    # ── 读写兼容接口 ──────────────────────────────

    def add(self, provider: str, email: str, cookie: str, password: str | None = None,
            credits: int = 0, status: str = "ok", note: str = "") -> None:
        now = time.time()
        if cookie == "mock-session":
            note = (note + " mock").strip()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO accounts (provider,email,password,cookie,credits,status,created_at,updated_at,note,cooling_since,borrowed_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,NULL,NULL)",
                (provider, email, password, cookie, credits, status, now, now, note))
            self._conn.commit()

    def list(self, provider: str | None = None, status: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM accounts", []
        conds = []
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
        rows = self._conn.execute(q + " ORDER BY created_at DESC", args).fetchall()
        return [dict(r) for r in rows]

    def get(self, provider: str) -> list[dict]:
        """某提供商当前就绪可用账号（含 cookie，供 Provider 用）。"""
        # 返回 active, ok, 以及短效未被锁定的账号
        rows = self._conn.execute(
            "SELECT * FROM accounts WHERE provider=? AND status IN ('ok', 'active') ORDER BY created_at DESC",
            (provider,)
        ).fetchall()
        return [dict(r) for r in rows]

    def update_credits(self, provider: str, email: str, credits: int) -> None:
        with self._lock:
            self._conn.execute("UPDATE accounts SET credits=?, updated_at=? WHERE provider=? AND email=?",
                               (credits, time.time(), provider, email))
            self._conn.commit()

    def mark(self, provider: str, email: str, status: str, note: str = "") -> None:
        now = time.time()
        cooling_since = now if status in ("cooling", "exhausted") else None
        with self._lock:
            self._conn.execute(
                "UPDATE accounts SET status=?, note=?, cooling_since=?, updated_at=? WHERE provider=? AND email=?",
                (status, note, cooling_since, now, provider, email))
            self._conn.commit()

    def set_checkin(self, provider: str, email: str, checkin_at: float) -> None:
        with self._lock:
            self._conn.execute("UPDATE accounts SET checkin_at=? WHERE provider=? AND email=?",
                               (checkin_at, provider, email))
            self._conn.commit()

    def counts(self) -> dict:
        """返回全状态细分统计 (映射为标准 key 与历史 key 兼容)。"""
        rows = self._conn.execute(
            "SELECT provider, status, COUNT(*) c FROM accounts GROUP BY provider, status").fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            p = r["provider"]
            st = r["status"]
            cnt = r["c"]
            prov_dict = out.setdefault(p, {
                "active": 0, "ok": 0,
                "working": 0,
                "cooling": 0, "exhausted": 0,
                "dead": 0, "banned": 0,
                "registering": 0, "unregistered": 0,
            })
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

    def total_credits(self, provider: str) -> int:
        r = self._conn.execute(
            "SELECT COALESCE(SUM(credits),0) s FROM accounts WHERE provider=? AND status IN ('ok', 'active', 'working')",
            (provider,)
        ).fetchone()
        return int(r["s"]) if r else 0

    # ── 自动补号 / 签到 / 延寿唤醒循环 ────────────────────────
    async def start(self) -> None:
        # 为长效签到型提供商（nanobanana）及 minimaxh3 开启自动补号与延寿巡检
        auto_provs = [p for p in ("nanobanana", "minimaxh3") if self._autoreg_enabled(p)]
        for prov in auto_provs:
            self.checkin_tasks[f"register:{prov}"] = asyncio.create_task(self._autoregister_loop(prov))
        # 每日签到与自动延寿巡检器
        self.checkin_tasks["nanobanana_checkin"] = asyncio.create_task(self._daily_checkin_loop("nanobanana"))
        self.checkin_tasks["wake_inspector"] = asyncio.create_task(self._cooling_wake_loop())
        log.info("号池 FSM 引擎启动：自动补号 %s + 签到与延寿唤醒巡检器就绪", auto_provs)

    @staticmethod
    def _autoreg_enabled(provider: str) -> bool:
        if provider == "minimaxh3":
            return os.getenv("IF_MINIMAXH3_AUTOREG", "1").strip().lower() in {"1", "true", "yes", "on"}
        return os.getenv("IF_NANOBANANA_AUTOREG", "1").strip().lower() in {"1", "true", "yes", "on"}

    async def stop(self) -> None:
        for t in self.checkin_tasks.values():
            t.cancel()
        if self.checkin_tasks:
            await asyncio.gather(*self.checkin_tasks.values(), return_exceptions=True)
        self.checkin_tasks.clear()

    async def _cooling_wake_loop(self) -> None:
        """延寿唤醒巡检：每 5 分钟扫描冷却账号并自动唤醒恢复。"""
        while True:
            try:
                await asyncio.sleep(300)
                for prov in ("nanobanana", "minimaxh3"):
                    self.wake_cooling_accounts(prov)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("延寿唤醒巡检器异常: %s", e)

    async def _autoregister_loop(self, provider: str) -> None:
        """提供商自动补号守护任务。"""
        target = TARGET_MINIMAXH3 if provider == "minimaxh3" else TARGET_NANOBANANA
        while True:
            try:
                if provider == "minimaxh3":
                    # 有积分的账号才算可用（minimaxh3 用完即弃）
                    usable = sum(1 for a in self.get(provider) if int(a.get("credits", 0) or 0) > 0)
                else:
                    usable = len(self.get(provider))
                if usable >= target:
                    if provider == "minimaxh3":
                        try:
                            from .providers import registry
                            prov = registry.providers.get("minimaxh3")
                            if prov:
                                await prov.refresh_credits()
                        except Exception:
                            pass
                    await asyncio.sleep(60)
                    continue
                reg = self.registerers.get(provider)
                if reg is None:
                    await asyncio.sleep(30)
                    continue

                try:
                    if not MOCK_REGISTER:
                        from .kookeey import kookeey_enabled
                        residential = [e for e in proxy_pool.entries if e.source == "residential" and e.available(time.time())]
                        free_ok = [e for e in proxy_pool.entries if e.source == "free" and e.available(time.time())]
                        if not (residential or free_ok or kookeey_enabled()):
                            log.info("号池补号暂停 %s：无可用出口代理", provider)
                            await asyncio.sleep(REGISTER_COOLDOWN)
                            continue
                    reg.proxy = await proxy_pool.acquire(prefer_source="residential")
                    acc = await reg.register_one()
                    if acc:
                        self.add(provider, acc["email"], acc["cookie"], acc.get("password"),
                                 credits=acc.get("credits", 0))
                        self.mark(provider, acc["email"], "ok")
                        log.info("号池补号成功 %s: %s（现有 %d）", provider, acc["email"], len(self.get(provider)))
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

    async def _daily_checkin_loop(self, provider: str) -> None:
        """nanobanana：定时检查签到（按时区与间隔）。"""
        while True:
            try:
                await asyncio.sleep(1800)  # 30 分钟一轮
                reg = self.registerers.get(provider)
                if reg is None:
                    continue
                now = time.time()
                for acc in self.list(provider, status="ok"):
                    last = acc.get("checkin_at") or 0
                    if now - last > 20 * 3600:  # 距上次签到 >20h → 补签
                        try:
                            ok = await reg.checkin(acc)
                            if ok:
                                self.set_checkin(provider, acc["email"], time.time())
                                self.update_credits(provider, acc["email"], ok)
                                self.mark(provider, acc["email"], "active")
                        except Exception as e:
                            log.warning("nanobanana 签到失败 %s: %s", acc["email"], e)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("签到循环异常 %s: %s", provider, e)

    def dashboard(self) -> dict:
        """前端「号池」看板数据：包含 minimaxh3、nanobanana 等所有受支持提供商。"""
        counts = self.counts()
        out = {}
        all_providers = set(counts.keys()) | {"nanobanana", "minimaxh3"}
        for prov in all_providers:
            c = counts.get(prov, {})
            # 兼容读取各状态计数
            ok_cnt = c.get("ok", 0) or c.get("active", 0)
            working_cnt = c.get("working", 0)
            exhausted_cnt = c.get("exhausted", 0) or c.get("cooling", 0)
            dead_cnt = c.get("dead", 0) or c.get("banned", 0)
            registering_cnt = c.get("registering", 0)
            unregistered_cnt = c.get("unregistered", 0)

            target = TARGET_MINIMAXH3 if prov == "minimaxh3" else TARGET_NANOBANANA
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
                "credits": self.total_credits(prov),
                "target": target,
                "auto_register": self.registerers.get(prov) is not None,
            }
        return out


# 模块级单例
account_pool = AccountPool()
