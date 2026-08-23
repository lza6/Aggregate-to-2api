"""邮箱池：多源临时邮箱（temp.tf 无敌十几亿 / temp-mail / 22.do）+ 注册记录。

契约（逆向确认）：
- temp.tf（无敌十几亿个）：POST https://temp.tf/api/check {email} → {data:[邮件], totalReceived}
  data 含收件；域名 high.edu.pl 等，量大可无限生成。
- temp-mail：GET https://web2.temp-mail.org/mailbox（Bearer JWT）→ 新邮箱；GET /messages → 邮件列表。
- 22.do：POST /action/mailbox/create → /login → /applyToken(JWT) → /action/mailbox/message。

核心职责：
- 为自动注册分配「未使用过」的邮箱（同一邮箱可注册多个网站，但记录用途，避免重复分配同一
  域名被注册过多触发风控）。
- 轮询收件：验证码/验证链接。
- 持久化邮箱→提供商注册记录（data/email_registry.db 或并入主 DB），重启不丢。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sqlite3
import threading
import time
from dataclasses import dataclass, field

import httpx

from . import config

log = logging.getLogger("email_pool")

DB_FILE = os.getenv("IF_EMAIL_DB_FILE", "data/email_registry.db")
# temp-mail 建箱最小间隔（秒）：防 429 限流。500 号 ≈ 500 箱 × 间隔。
EMAIL_CREATE_MIN_INTERVAL = int(os.getenv("IF_EMAIL_CREATE_INTERVAL", "30"))
EMAIL_CREATE_BACKOFF = int(os.getenv("IF_EMAIL_CREATE_BACKOFF", "60"))


@dataclass
class MailSource:
    """统一邮箱源接口。"""
    name: str
    session: httpx.AsyncClient | None = field(default=None, repr=False)

    async def new_address(self) -> tuple[str, dict]:
        """生成一个新邮箱，返回 (address, state)。state 供收件用。"""
        raise NotImplementedError

    async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
        """取该邮箱收到的邮件列表。"""
        raise NotImplementedError


# ── temp.tf（无敌十几亿个邮箱）────────────────────
class TempTfSource(MailSource):
    name = "temp.tf"
    _domains = ["high.edu.pl", "duck.com", "temp.tf", "jetable.net"]

    def __init__(self) -> None:
        super().__init__(name=self.name)
        self.session = httpx.AsyncClient(timeout=15.0, headers={"User-Agent": config.USER_AGENT})

    async def new_address(self) -> tuple[str, dict]:
        # 纯本地随机生成（无需网络），10 位小写字母数字 → 百万亿级空间
        local = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=10))
        domain = random.choice(self._domains)
        return f"{local}@{domain}", {"source": self.name, "domain": domain}

    async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
        """POST /api/check 取该邮箱收到的邮件（data 列表，空=暂无）。"""
        try:
            r = await self.session.post("https://temp.tf/api/check", json={"email": address})
            if r.status_code == 200:
                return r.json().get("data") or []
        except Exception as e:
            log.warning("temp.tf 收件失败 %s: %s", address, e)
        return []


# ── temp-mail.org（web2 API）───────────────────────
class TempMailSource(MailSource):
    """temp-mail.org 收件源：web2.temp-mail.org 建箱拿 mailbox + Bearer JWT，轮询收件。

    逆向（邮箱链接如.txt）：`GET https://web2.temp-mail.org/messages`（Bearer JWT）→ 列表；
    `GET /messages/{id}` → 邮件详情（bodyHtml 含 verify 链接）。
    nanobanana / minimaxh3 验证邮件能被 temp-mail 收录（temp.tf 收不到 resend 发件）。
    """

    name = "temp-mail"
    API = "https://web2.temp-mail.org"
    _domains = ["beiwoh.com", "hutdot.com"]

    def __init__(self) -> None:
        super().__init__(name=self.name)
        self._last_create = 0.0  # 建箱限流节流（429 防护）
        self.session = httpx.AsyncClient(timeout=15.0,
                                         headers={"User-Agent": config.USER_AGENT,
                                                  "Origin": "https://temp-mail.org",
                                                  "Referer": "https://temp-mail.org/"})

    async def new_address(self) -> tuple[str, dict]:
        # chatgpt2api 逆向确认：POST /mailbox（空 body）→ {token, mailbox}（建箱+拿 JWT）。
        # temp-mail 有建箱限流（429 Too Many Request）——加最小间隔 + 失败退避，防批量注册触发。
        now = time.time()
        gap = now - self._last_create
        if gap < EMAIL_CREATE_MIN_INTERVAL:
            await asyncio.sleep(EMAIL_CREATE_MIN_INTERVAL - gap)
        r = await self.session.post(f"{self.API}/mailbox", json={},
                                    headers={"Content-Type": "application/json"})
        self._last_create = time.time()
        if r.status_code == 429:
            log.warning("temp-mail 建箱限流(429)，退避 %ds", EMAIL_CREATE_BACKOFF)
            await asyncio.sleep(EMAIL_CREATE_BACKOFF)
            raise RuntimeError("temp-mail 建箱限流，稍后重试")
        if r.status_code != 200:
            raise RuntimeError(f"temp-mail 建箱失败 HTTP {r.status_code}")
        data = r.json()
        address = str(data.get("mailbox") or "")
        token = str(data.get("token") or "")
        if "@" not in address or not token:
            raise RuntimeError(f"temp-mail 返回异常: {str(data)[:150]}")
        return address, {"source": self.name, "token": token}

    async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
        """GET /messages 带 Bearer JWT → 邮件列表（逆向确认）。"""
        token = (state or {}).get("token")
        if not token:
            return []
        try:
            r = await self.session.get(f"{self.API}/messages",
                                       headers={"Authorization": f"Bearer {token}"})
            if r.status_code == 200:
                msgs = r.json()
                # 兼容响应：数组 或 {messages:[...]} 或 {data:[...]}
                if isinstance(msgs, list):
                    return msgs
                if isinstance(msgs, dict):
                    for k in ("messages", "data", "mailbox"):
                        v = msgs.get(k)
                        if isinstance(v, list):
                            return v
                return []
        except Exception as e:
            log.warning("temp-mail 收件失败 %s: %s", address, e)
        return []


# ── 22.do（免费临时邮箱，REST 全链路，实测可用）──────
class Do22Source(MailSource):
    """22.do 免费临时邮箱（chatgpt2api 逆向确认，服务器实测建箱 200 无限流）。

    契约：
      POST /action/mailbox/create  {type:'random'} -> {data:{email,...}}
      POST /action/mailbox/login   {email,language:'en-US'} -> set-cookie email
      POST /action/mailbox/applyToken {email,uuid:<随机>} -> {data:{token:JWT}}
      POST /action/mailbox/message {email,lastime:0} + Bearer JWT -> {data:[...]}（含验证码/验证链接）
    """

    name = "22.do"
    BASE = "https://22.do"

    def __init__(self) -> None:
        super().__init__(name=self.name)
        self.session = httpx.AsyncClient(timeout=15.0,
                                         headers={"User-Agent": config.USER_AGENT,
                                                  "Content-Type": "application/json",
                                                  "Origin": self.BASE, "Referer": f"{self.BASE}/",
                                                  "Accept": "*/*"})

    async def new_address(self) -> tuple[str, dict]:
        import uuid
        r = await self.session.post(f"{self.BASE}/action/mailbox/create",
                                    json={"type": "random"})
        if r.status_code != 200:
            raise RuntimeError(f"22.do 建箱失败 HTTP {r.status_code}")
        data = (r.json() or {}).get("data") or {}
        address = str(data.get("email") or "")
        if "@" not in address:
            raise RuntimeError(f"22.do 返回异常: {str(data)[:150]}")
        # login 拿 email cookie（message 接口需要）
        await self.session.post(f"{self.BASE}/action/mailbox/login",
                                json={"email": address, "language": "en-US"})
        # applyToken 拿 JWT（message 鉴权）
        token_resp = await self.session.post(f"{self.BASE}/action/mailbox/applyToken",
                                             json={"email": address,
                                                   "uuid": uuid.uuid4().hex})
        token = ((token_resp.json() or {}).get("data") or {}).get("token") or ""
        return address, {"source": self.name, "email": address, "token": token}

    async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
        email = (state or {}).get("email") or address
        token = (state or {}).get("token")
        if not token:
            return []
        try:
            r = await self.session.post(f"{self.BASE}/action/mailbox/message",
                                        json={"email": email, "lastime": 0},
                                        headers={"Authorization": f"Bearer {token}"})
            if r.status_code == 200:
                return (r.json() or {}).get("data") or []
        except Exception as e:
            log.warning("22.do 收件失败 %s: %s", address, e)
        return []


from .email_sources_linshi import LinshiEmailSource

# ── 邮箱池管理器 ──────────────────────────────────
class EmailPool:
    def __init__(self, db_path: str = DB_FILE) -> None:
        self._sources = [TempTfSource(), TempMailSource(), Do22Source(), LinshiEmailSource()]
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()
        self._used: set[str] = self._load_used()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS email_registry (
                email       TEXT PRIMARY KEY,
                provider    TEXT NOT NULL,
                registered_at REAL,
                status      TEXT DEFAULT 'ok',
                note        TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_email_provider ON email_registry(provider);
            """)
            self._conn.commit()

    def _load_used(self) -> set[str]:
        rows = self._conn.execute("SELECT email FROM email_registry").fetchall()
        return {r["email"] for r in rows}

    # ── 分配 ──────────────────────────────────────
    async def allocate(self, provider: str, want_fresh: bool = True,
                       prefer_source: str | None = None,
                       prefer_domain: str | None = None) -> tuple[str, object]:
        """分配一个邮箱给指定提供商。

        prefer_source：指定源（"temp-mail"/"temp.tf"）。nanobanana/minimaxh3 验证邮件
        只有 temp-mail 能收 → 指定 temp-mail；该源失败时**不 fallback 到会被站点拒的 temp.tf**（明确失败）。
        默认：优先 temp-mail（能收 verify），temp.tf 兜底（量大，用于不需要收件的场景）。
        want_fresh=True 强制全新（未注册过任何网站）。
        返回 (email, source_state)。source_state 含 source 名与收件 token。
        """
        if prefer_source:
            src = next((s for s in self._sources if s.name == prefer_source), None)
            if src is None:
                raise RuntimeError(f"邮箱源 {prefer_source} 不存在")
            # 指定源：失败即抛（不 fallback），避免给站点不接受的邮箱
            try:
                address, st = await src.new_address()
            except Exception as e:
                raise RuntimeError(f"邮箱源 {prefer_source} 建箱失败: {e}")
            if not address or "@" not in address or address in self._used:
                raise RuntimeError(f"邮箱源 {prefer_source} 返回异常邮箱")
            self._used.add(address)
            return address, st
        # 默认：优先 22.do 与 linshi-email（经实测 100% 畅通且收真实验证邮件），temp-mail 备用，temp.tf 兜底
        sources = [s for s in self._sources if s.name in ("22.do", "linshi-email", "temp-mail")] + [s for s in self._sources if s.name == "temp.tf"]
        for _ in range(15):
            src = sources[_ % len(sources)]
            try:
                address, st = await src.new_address()
            except Exception as e:
                log.warning("邮箱源 %s 建箱失败: %s", src.name, e)
                continue
            if address and address not in self._used and "@" in address:
                self._used.add(address)
                return address, st
        raise RuntimeError("邮箱池分配失败（15 次碰撞）")

    # ── 收件 ──────────────────────────────────────
    async def wait_for_mail(self, address: str, source_state: object, timeout: float = 90.0,
                            contains: str | None = None) -> dict | None:
        """轮询直到该邮箱收到含关键词的邮件（验证码/验证链接）。source_state 携源与 token。"""
        name = (source_state or {}).get("source", "temp.tf")
        src = next((s for s in self._sources if s.name == name), self._sources[0])
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            mails = await src.fetch_mails(address, source_state)
            for mail in mails:
                blob = json.dumps(mail, ensure_ascii=False)
                if contains and contains.lower() not in blob.lower():
                    continue
                return mail
            await asyncio.sleep(2.0)
        return None

    # ── 记录 ──────────────────────────────────────
    def record(self, email: str, provider: str, status: str = "ok", note: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO email_registry (email, provider, registered_at, status, note)"
                " VALUES (?, ?, ?, ?, ?)",
                (email, provider, time.time(), status, note))
            self._conn.commit()

    def registered_providers(self, email: str) -> list[str]:
        rows = self._conn.execute("SELECT provider FROM email_registry WHERE email=?", (email,)).fetchall()
        return [r["provider"] for r in rows]

    def stats(self) -> dict:
        total = self._conn.execute("SELECT COUNT(*) FROM email_registry").fetchone()[0]
        by_provider = dict(self._conn.execute(
            "SELECT provider, COUNT(*) FROM email_registry GROUP BY provider").fetchall())
        return {"total_registered": total, "by_provider": by_provider}


# 模块级单例
email_pool = EmailPool()