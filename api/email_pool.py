"""邮箱池：多源弹性邮箱池管理器（EmailPool）+ 注册记录持久化。

P2-4（v7.3）：9 个邮箱 Source 适配器类已拆分到 `api/email_sources/` 子包
（base/linshi/mailtm/guerrilla/custom_imap/do22/tempmail/tempmailio/mailgw/temptf），
本模块保留池管理器（策略选择/分配/收件轮询/记录/风控）与 DB 持久化。

向后兼容：本模块顶部 re-export 全部 Source 类，`from api.email_pool import
LinshiMailSource` 等旧 import 路径仍可用。

支持多源临时与自建邮箱提供商：
1. LinshiMailSource (linshi-email.com 免费临时邮箱，零 429，极速)
2. MailTmSource (mail.tm REST API，速度快且稳定，支持动态创建 account 并基于 JWT 拉取 messages)
3. MailGwSource (api.mail.gw REST API，自建邮箱，动态域名 + JWT 拉信)
4. GuerrillaMailSource (GuerrillaMail 免认证公共/私有临时邮箱与邮件抓取)
5. CustomImapSource (自建域名邮箱通配符捕捉，支持通过 IMAP4/IMAP4_SSL 异步非阻塞读取)
6. Do22Source (22.do 免费临时邮箱，REST 全链路)
7. TempMailSource (temp-mail.org web2 API)
8. TempMailIoSource (temp-mail.io REST API，无 key 免费源)
9. TempTfSource (temp.tf 十几亿级随机邮箱)

核心职责：
- 为自动注册分配「未使用过」的邮箱，按优先级、可用性评分与风控状态自适应轮换。
- 某邮箱源遭遇 429 或故障时自动退避并平滑切换到备用源。
- 轮询收件：验证码/验证链接精准提取。
- 持久化邮箱与域名注册记录到 SQLite（aiosqlite，P2-3 v7.2 迁移），重启不丢。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import aiosqlite

from .email_sources import (  # noqa: F401  (re-export 供旧 import 路径使用)
    BaseMailSource,
    CustomImapSource,
    Do22Source,
    GuerrillaMailSource,
    LinshiEmailSource,
    LinshiMailSource,
    MailGwSource,
    MailSource,
    MailTmSource,
    TempMailIoSource,
    TempMailSource,
    TempTfSource,
)
from .email_sources._limits import EMAIL_CREATE_BACKOFF, EMAIL_CREATE_MIN_INTERVAL  # noqa: F401

log = logging.getLogger("email_pool")

DB_FILE = os.getenv("IF_EMAIL_DB_FILE", "data/email_registry.db")
# temp-mail 建箱限速常量定义在 email_sources/_limits.py（单一来源），
# 此处 re-import 保持 `from api.email_pool import EMAIL_CREATE_MIN_INTERVAL` 兼容。


# ── 邮箱池管理器 ──────────────────────────────────
class EmailPool:
    """具备多源策略、优先级感知、可用性评分与自动故障退避的弹性邮箱池管理器。"""

    # 别名映射
    _ALIASES: dict[str, str] = {
        "linshi": "linshi-email",
        "linshi-email": "linshi-email",
        "linshimail": "linshi-email",
        "mailtm": "mail.tm",
        "mail.tm": "mail.tm",
        "guerrilla": "guerrillamail",
        "guerrillamail": "guerrillamail",
        "imap": "custom-imap",
        "custom-imap": "custom-imap",
        "22do": "22.do",
        "22.do": "22.do",
        "tempmail": "temp-mail",
        "temp-mail": "temp-mail",
        "tempmailio": "temp-mail.io",
        "tempmail.io": "temp-mail.io",
        "temp-mail.io": "temp-mail.io",
        "mailgw": "mail.gw",
        "mail.gw": "mail.gw",
        "temptf": "temp.tf",
        "temp.tf": "temp.tf",
    }

    def __init__(self, db_path: str = DB_FILE, custom_sources: list[BaseMailSource] | None = None) -> None:
        if custom_sources is not None:
            self._sources: list[BaseMailSource] = list(custom_sources)
        else:
            self._sources = [
                CustomImapSource(),
                LinshiMailSource(),
                MailTmSource(),
                MailGwSource(),
                Do22Source(),
                GuerrillaMailSource(),
                TempMailSource(),
                TempMailIoSource(),
                TempTfSource(),
            ]
        # P2-3（v7.2.0）：sqlite3 + threading.Lock → aiosqlite + asyncio.Lock，
        # 与 db/core.py / account_pool.py 一致，消除 async 路径（registerer.register_one）
        # 直接触发同步 sqlite3 I/O 阻塞事件循环的隐患。连接在 _ensure_conn 惰性创建。
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._initialized = False
        self._pool_loop: asyncio.AbstractEventLoop | None = None
        self._used: set[str] = set()

    async def _ensure_conn(self) -> aiosqlite.Connection:
        """惰性创建/复用 aiosqlite 连接，绑定当前 loop（跨 loop 重建）。"""
        cur_loop = asyncio.get_running_loop()
        if self._conn is not None and self._pool_loop is cur_loop and not self._conn._connection:
            self._conn = None
            self._initialized = False
        if self._conn is None or self._pool_loop is not cur_loop:
            if self._pool_loop is not None and self._pool_loop is not cur_loop:
                await self._close_conn_safe()
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
                self._used = await self._load_used(conn)
                self._initialized = True
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
        async with self._lock:
            await conn.executescript("""
            CREATE TABLE IF NOT EXISTS email_registry (
                email       TEXT PRIMARY KEY,
                provider    TEXT NOT NULL,
                registered_at REAL,
                status      TEXT DEFAULT 'ok',
                note        TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_email_provider ON email_registry(provider);

            CREATE TABLE IF NOT EXISTS domain_risk (
                domain      TEXT PRIMARY KEY,
                fail_count  INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                status      TEXT DEFAULT 'ok',
                last_updated REAL
            );
            """)
            await conn.commit()

    async def _load_used(self, conn: aiosqlite.Connection) -> set[str]:
        cur = await conn.execute("SELECT email FROM email_registry")
        rows = await cur.fetchall()
        return {r["email"] for r in rows}

    def _find_source(self, name: str) -> BaseMailSource | None:
        canonical = self._ALIASES.get(name.lower().strip(), name.lower().strip())
        for src in self._sources:
            if src.name == canonical or src.name == name:
                return src
        return None

    async def risky_domains(self, min_fails: int = 3) -> set[str]:
        """返回失败次数 >= min_fails 的拉黑域名集合（供 allocate 过滤）。"""
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT domain FROM domain_risk WHERE fail_count >= ? AND status = 'risky'",
                (min_fails,),
            )
            rows = await cur.fetchall()
        return {r["domain"] for r in rows}

    def get_sources(self) -> list[BaseMailSource]:
        """获取当前配置的所有邮箱源副本。"""
        return list(self._sources)

    # ── 分配 ──────────────────────────────────────
    async def allocate(
        self,
        provider: str,
        want_fresh: bool = True,
        prefer_source: str | None = None,
        prefer_domain: str | None = None,
    ) -> tuple[str, dict]:
        """为指定提供商分配一个有效邮箱。

        支持指定源（prefer_source）及按评分+退避状态动态轮换。

        allocate 本身已是 async（内部 await src.new_address）；P2-3 后 risky_domains
        也已 async，直接 await（aiosqlite 内部线程池处理 I/O，不阻塞 loop）。
        """
        # 1) 指定特定邮箱源
        if prefer_source:
            src = self._find_source(prefer_source)
            if src is None:
                raise RuntimeError(f"邮箱源 {prefer_source} 不存在")
            try:
                address, st = await src.new_address()
                if not address or "@" not in address or (want_fresh and address in self._used):
                    raise RuntimeError(f"邮箱源 {prefer_source} 返回重复或无效邮箱: {address}")
                src.mark_success()
                self._used.add(address)
                return address, st
            except Exception as e:
                src.mark_failure(str(e))
                raise RuntimeError(f"邮箱源 {prefer_source} 建箱失败: {e}")

        # 2) 动态策略选择：按 score() 降序排序可用源
        candidate_sources = sorted(self._sources, key=lambda s: s.score(), reverse=True)
        # 过滤掉无法使用（如未配置的 IMAP）且 score < -50 的不可用源
        active_sources = [s for s in candidate_sources if s.is_available() and s.priority > 0]
        if not active_sources:
            # 全部处于冷却或无可用源，回退到兜底源
            active_sources = [s for s in candidate_sources if s.priority > 0] or self._sources

        errors: list[str] = []
        risky = await self.risky_domains()  # 已被上游拉黑的域名（连续失败 >=3）
        for _ in range(15):
            src = active_sources[_ % len(active_sources)]
            try:
                address, st = await src.new_address()
            except Exception as e:
                src.mark_failure(str(e))
                errors.append(f"{src.name}: {e}")
                log.warning("邮箱源 %s 建箱失败: %s，切换备用源", src.name, e)
                continue

            if not address or "@" not in address:
                src.mark_failure("返回空或无效地址")
                continue

            # 跳过已被上游拉黑的域名（INVALID_EMAIL 风控记录）
            domain = address.split("@")[-1].lower()
            if domain in risky:
                log.info("跳过拉黑域名邮箱 %s（domain_risk fail>=3）", address)
                continue

            if want_fresh and address in self._used:
                continue

            # 若有指定域名偏好，检查是否符合
            if prefer_domain and not address.endswith(f"@{prefer_domain.lstrip('@')}"):
                continue

            src.mark_success()
            self._used.add(address)
            return address, st

        raise RuntimeError(f"邮箱池分配失败（15 次尝试均未成功，最近错误: {'; '.join(errors[-3:])}）")

    # ── 收件 ──────────────────────────────────────
    async def wait_for_mail(
        self,
        address: str,
        source_state: dict | None,
        timeout: float = 90.0,
        contains: str | None = None,
    ) -> dict | None:
        """轮询直到该邮箱收到含指定关键词的邮件（验证码/验证链接）。

        wait_for_mail 本身已是 async（内部 await src.fetch_mails），不直接触碰
        self._conn / self._lock——保留为 async 入口。async 调用方直接 await 即可，
        无需 to_thread 包装（无同步 sqlite3 I/O）。
        """
        name = (source_state or {}).get("source", "")
        src = self._find_source(name) if name else None
        if src is None:
            src = self._sources[0]

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                mails = await src.fetch_mails(address, source_state)
                for mail in mails:
                    blob = json.dumps(mail, ensure_ascii=False)
                    if contains and contains.lower() not in blob.lower():
                        continue
                    src.mark_success()
                    return mail
            except Exception as e:
                log.debug("收件轮询异常 %s: %s", address, e)
            await asyncio.sleep(2.0)
        return None

    # ── 记录与风控 ──────────────────────────────────
    async def record(self, email: str, provider: str, status: str = "ok", note: str = "") -> None:
        """记录邮箱注册结果 + 域名风控（P2-3 后 async + aiosqlite）。"""
        conn = await self._ensure_conn()
        async with self._lock:
            await conn.execute(
                "INSERT OR REPLACE INTO email_registry (email, provider, registered_at, status, note)"
                " VALUES (?, ?, ?, ?, ?)",
                (email, provider, time.time(), status, note),
            )
            domain = email.split("@")[-1] if "@" in email else ""
            if domain:
                if status == "ok":
                    await conn.execute(
                        """INSERT INTO domain_risk (domain, success_count, last_updated)
                           VALUES (?, 1, ?)
                           ON CONFLICT(domain) DO UPDATE SET
                           success_count = success_count + 1,
                           last_updated = excluded.last_updated""",
                        (domain, time.time()),
                    )
                else:
                    await conn.execute(
                        """INSERT INTO domain_risk (domain, fail_count, status, last_updated)
                           VALUES (?, 1, 'risky', ?)
                           ON CONFLICT(domain) DO UPDATE SET
                           fail_count = fail_count + 1,
                           last_updated = excluded.last_updated""",
                        (domain, time.time()),
                    )
            await conn.commit()

    async def async_record(
        self, email: str, provider: str, status: str = "ok", note: str = ""
    ) -> None:
        """record 的 async 兼容别名（P2-3 后 record 已 async，直接 await）。"""
        await self.record(email, provider, status, note)

    async def registered_providers(self, email: str) -> list[str]:
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute("SELECT provider FROM email_registry WHERE email=?", (email,))
            rows = await cur.fetchall()
        return [r["provider"] for r in rows]

    async def stats(self) -> dict:
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute("SELECT COUNT(*) FROM email_registry")
            total = (await cur.fetchone())[0]
            cur = await conn.execute("SELECT provider, COUNT(*) FROM email_registry GROUP BY provider")
            by_provider = dict(await cur.fetchall())
            cur = await conn.execute("SELECT status, COUNT(*) FROM email_registry GROUP BY status")
            by_status = dict(await cur.fetchall())
        sources_status = [
            {
                "name": s.name,
                "priority": s.priority,
                "score": round(s.score(), 1),
                "is_available": s.is_available(),
                "success_count": s.success_count,
                "failure_count": s.failure_count,
                "last_error": s.last_error,
            }
            for s in self._sources
        ]
        return {
            "total_registered": total,
            "by_provider": by_provider,
            "by_status": by_status,
            "successful_registrations": int(by_status.get("ok", 0)),
            "failed_registrations": int(by_status.get("error", 0)),
            "sources": sources_status,
        }


# 模块级单例
email_pool = EmailPool()
