"""号池（账号池）：积分制提供商的账号管理 + 自动补号 + 每日签到。

覆盖：
- minimaxh3（用完即丢，自动注册补号，目标常驻 500 个）
- nanobanana-pro（每日签到续额，非用完即丢，每天自动签到）

职责：
- 持久化账号（cookie/邮箱/密码/余额/签到状态）到 data/account_pool.db
- 各提供商按需取号（round-robin / 余额排序）
- 自动补号循环（minimaxh3 余额<阈值 → 触发注册器补号；nanobanana 每日签到）
- 看板：每个提供商实时账号数/可用余额/注册统计/正在注册数（前端「号池」页）
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time

from . import config
from .proxy_pool import proxy_pool
from .providers.base import MOCK_REGISTER

log = logging.getLogger("account_pool")

DB_FILE = os.getenv("IF_ACCOUNT_DB_FILE", "data/account_pool.db")
# minimaxh3 目标常驻账号数（用户要求 500）
TARGET_MINIMAXH3 = int(os.getenv("IF_MINIMAXH3_ACCOUNT_TARGET", "500"))
# nanobanana 目标常驻账号数
TARGET_NANOBANANA = int(os.getenv("IF_NANOBANANA_ACCOUNT_TARGET", "500"))
# 补号冷却（秒）：注册器连续失败时退避，防风控
REGISTER_COOLDOWN = int(os.getenv("IF_REGISTER_COOLDOWN", "120"))


class AccountPool:
    def __init__(self, db_path: str = DB_FILE) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()
        # 注册器/签到器注入（避免循环 import）
        self.registerers: dict[str, object] = {}
        self.checkin_tasks: dict[str, asyncio.Task] = {}
        # 看板状态
        self.stats: dict[str, dict] = {}

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                provider    TEXT NOT NULL,
                email       TEXT NOT NULL,
                password    TEXT,
                cookie      TEXT,
                credits     INTEGER DEFAULT 0,
                status      TEXT DEFAULT 'ok',       -- ok | exhausted | banned | registering
                checkin_at  REAL,                     -- nanobanana 上次签到时间
                created_at  REAL,
                updated_at  REAL,
                note        TEXT,
                PRIMARY KEY (provider, email)
            );
            CREATE INDEX IF NOT EXISTS idx_acc_provider_status ON accounts(provider, status);
            """)
            self._conn.commit()

    # ── 读写 ──────────────────────────────────────
    def add(self, provider: str, email: str, cookie: str, password: str | None = None,
            credits: int = 0, status: str = "ok", note: str = "") -> None:
        now = time.time()
        # M1(审计修复): mock 账号（测试残留）打标记，生产加载时过滤，防泄漏到线上
        if cookie == "mock-session":
            note = (note + " mock").strip()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO accounts (provider,email,password,cookie,credits,status,created_at,updated_at,note)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (provider, email, password, cookie, credits, status, now, now, note))
            self._conn.commit()

    def list(self, provider: str | None = None, status: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM accounts", []
        conds = []
        if provider:
            conds.append("provider=?"); args.append(provider)
        if status:
            conds.append("status=?"); args.append(status)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        rows = self._conn.execute(q + " ORDER BY created_at DESC", args).fetchall()
        return [dict(r) for r in rows]

    def get(self, provider: str) -> list[dict]:
        """某提供商当前可用账号（含 cookie，供 Provider 用）。"""
        return self.list(provider, status="ok")

    def update_credits(self, provider: str, email: str, credits: int) -> None:
        with self._lock:
            self._conn.execute("UPDATE accounts SET credits=?, updated_at=? WHERE provider=? AND email=?",
                               (credits, time.time(), provider, email))
            self._conn.commit()

    def mark(self, provider: str, email: str, status: str, note: str = "") -> None:
        with self._lock:
            self._conn.execute("UPDATE accounts SET status=?, note=?, updated_at=? WHERE provider=? AND email=?",
                               (status, note, time.time(), provider, email))
            self._conn.commit()

    def set_checkin(self, provider: str, email: str, checkin_at: float) -> None:
        with self._lock:
            self._conn.execute("UPDATE accounts SET checkin_at=? WHERE provider=? AND email=?",
                               (checkin_at, provider, email))
            self._conn.commit()

    def counts(self) -> dict:
        rows = self._conn.execute(
            "SELECT provider, status, COUNT(*) c FROM accounts GROUP BY provider, status").fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            out.setdefault(r["provider"], {})[r["status"]] = r["c"]
        return out

    def total_credits(self, provider: str) -> int:
        r = self._conn.execute(
            "SELECT COALESCE(SUM(credits),0) s FROM accounts WHERE provider=? AND status='ok'", (provider,)).fetchone()
        return int(r["s"])

    # ── 自动补号 / 签到循环 ────────────────────────
    async def start(self) -> None:
        # 补号循环按配置开关；minimaxh3 若 turnstile 被站点拒（外部求解兼容）可经 IF_MINIMAXH3_AUTOREG=0 关闭，
        # 避免无谓消耗 cf_solver 单槽（主站 token 预取优先）。nanobanana 每日签到续额。
        auto_provs = [p for p in ("minimaxh3", "nanobanana") if self._autoreg_enabled(p)]
        for prov in auto_provs:
            self.checkin_tasks[f"register:{prov}"] = asyncio.create_task(self._autoregister_loop(prov))
        # 每日签到（nanobanana 续额）
        self.checkin_tasks["nanobanana"] = asyncio.create_task(self._daily_checkin_loop("nanobanana"))
        log.info("号池启动：自动补号 %s + 每日签到循环已就绪", auto_provs)

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

    async def _autoregister_loop(self, provider: str) -> None:
        """minimaxh3：可用账号 < TARGET 时持续补号（注册器注入）。

        M7(审计修复)：每号从代理池轮换出口 IP（防批量注册同 IP 风控；池空回退直连）。
        H3(审计修复)：minimaxh3 目标按「有可用积分账号」统计；账号耗尽 mark exhausted；
        定期 refresh_credits 恢复上游余额（号可能被别的实例用掉/上游重置）。
        M5(审计修复)：成功注册后也节流（不能连发打爆上游）。
        """
        target = TARGET_MINIMAXH3 if provider == "minimaxh3" else TARGET_NANOBANANA
        while True:
            try:
                if provider == "minimaxh3":
                    # H3: 有积分的账号才算可用（minimaxh3 用完即弃）
                    usable = sum(1 for a in self.get(provider) if int(a.get("credits", 0) or 0) > 0)
                else:
                    usable = len(self.get(provider))
                if usable >= target:
                    # H3: 定期刷新上游余额（恢复被耗尽账号；nanobanana 由签到续额）
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
                # 注册 1 个（单次），记录看板
                try:
                    # M7: 每号轮换代理。注册流量含邮箱/密码/验证链接——安全红线：
                    # 仅住宅代理可用时注册（proxy_pool.residential 或 kookeey 付费住宅）；
                    # 免费代理明文无认证会泄露凭据（M10），服务器直连 IP 会被上游风控。
                    # kookeey 可用时 registerer 会用 kookeey(email) 每号粘性住宅 IP，无需 proxy_pool。
                    # M99(审计修复): mock 注册（IF_MOCK_REGISTER=1）不碰真实上游 → 跳过住宅代理守卫，
                    # 任何环境下都能注册出 mock 账号，E2E 号池/路由断言才成立。
                    if not MOCK_REGISTER:
                        from .kookeey import kookeey_enabled
                        residential = [e for e in proxy_pool.entries if e.source == "residential" and e.available(time.time())]
                        if not (residential or kookeey_enabled()):
                            log.info("号池补号暂停 %s：无住宅代理（配 IF_KOOKEEY 或 IF_PROXY_FILE；批量可用 inject_accounts --real）", provider)
                            await asyncio.sleep(REGISTER_COOLDOWN)
                            continue
                    reg.proxy = await proxy_pool.acquire(prefer_source="residential")
                    acc = await reg.register_one()
                    if acc:
                        self.add(provider, acc["email"], acc["cookie"], acc.get("password"),
                                 credits=acc.get("credits", 0))
                        self.mark(provider, acc["email"], "ok")
                        log.info("号池补号成功 %s: %s（现有 %d）", provider, acc["email"], len(self.get(provider)))
                        await asyncio.sleep(REGISTER_COOLDOWN)  # M5: 成功也节流
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
        """nanobanana：每 30 分钟检查，未签到的账号签到（按美区时区重置）。"""
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
                        except Exception as e:
                            log.warning("nanobanana 签到失败 %s: %s", acc["email"], e)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("签到循环异常 %s: %s", provider, e)

    def dashboard(self) -> dict:
        """前端「号池」看板数据。"""
        counts = self.counts()
        out = {}
        for prov in ("minimaxh3", "nanobanana"):
            c = counts.get(prov, {})
            out[prov] = {
                "total": sum(c.values()),
                "ok": c.get("ok", 0),
                "exhausted": c.get("exhausted", 0),
                "registering": c.get("registering", 0),
                "credits": self.total_credits(prov),
                "target": TARGET_MINIMAXH3 if prov == "minimaxh3" else TARGET_NANOBANANA,
                "auto_register": self.registerers.get(prov) is not None,
            }
        return out


# 模块级单例
account_pool = AccountPool()
