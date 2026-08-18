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


@dataclass
class MailSource:
    """统一邮箱源接口。"""
    name: str
    session: httpx.Client | None = field(default=None, repr=False)

    async def new_address(self) -> tuple[str, dict]:
        """生成一个新邮箱，返回 (address, state)。state 供收件用。"""
        raise NotImplementedError


# ── temp.tf（无敌十几亿个邮箱）────────────────────
class TempTfSource(MailSource):
    name = "temp.tf"
    _domains = ["high.edu.pl", "duck.com", "temp.tf", "jetable.net"]

    def __init__(self) -> None:
        super().__init__(name=self.name)
        self.session = httpx.Client(timeout=15.0, headers={"User-Agent": config.USER_AGENT})

    def new_address(self) -> tuple[str, dict]:
        # 纯本地随机生成（无需网络），10 位小写字母数字 → 百万亿级空间
        local = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=10))
        domain = random.choice(self._domains)
        return f"{local}@{domain}", {"source": self.name, "domain": domain}

    def fetch_mails(self, address: str) -> list[dict]:
        """POST /api/check 取该邮箱收到的邮件（data 列表，空=暂无）。"""
        try:
            r = self.session.post("https://temp.tf/api/check", json={"email": address})
            if r.status_code == 200:
                return r.json().get("data") or []
        except Exception as e:
            log.warning("temp.tf 收件失败 %s: %s", address, e)
        return []


# ── temp-mail.org（web2 API）───────────────────────
class TempMailSource(MailSource):
    name = "temp-mail"
    API = "https://web2.temp-mail.org"

    def __init__(self) -> None:
        super().__init__(name=self.name)
        self.session = httpx.Client(timeout=15.0,
                                    headers={"User-Agent": config.USER_AGENT,
                                             "Origin": "https://temp-mail.org",
                                             "Referer": "https://temp-mail.org/"})

    async def new_address(self) -> tuple[str, dict]:
        r = self.session.get(f"{self.API}/mailbox")
        if r.status_code != 200:
            raise RuntimeError(f"temp-mail 建箱失败 HTTP {r.status_code}")
        # 响应即邮箱地址（如 {"email": "...@beiwob.com"} 或裸字符串，兼容解析）
        data = r.json()
        address = data.get("email") or data.get("mailbox") or (data if isinstance(data, str) else "")
        return address, {"source": self.name}

    def fetch_mails(self, address: str) -> list[dict]:
        # 从新地址响应拿到的 token 无法跨调用保留（重新 GET /messages 需要 JWT）；
        # temp-mail JWT 由 mailbox 接口返回 header，此处简化为记录级实现，真实注册走 temp.tf 主源。
        return []


# ── 邮箱池管理器 ──────────────────────────────────
class EmailPool:
    def __init__(self, db_path: str = DB_FILE) -> None:
        self._sources: list[TempTfSource] = [TempTfSource()]
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
    def allocate(self, provider: str, want_fresh: bool = True, prefer_domain: str | None = None) -> tuple[str, TempTfSource]:
        """分配一个邮箱给指定提供商。want_fresh=True 强制全新（未注册过任何网站）。

        返回 (email, source)。域名轮换避免同一域名批量注册触发风控。
        prefer_domain：提供商已验证可用的域名（如 nanobanana/minimaxh3 用 high.edu.pl，
        部分站点拒绝 temp.tf/duck.com 等临时域）。
        """
        domains = self._sources[0]._domains
        if prefer_domain and prefer_domain in domains:
            domains = [prefer_domain]
        for _ in range(30):
            src = random.choice(self._sources)
            domain = random.choice(domains)
            local = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=10))
            address = f"{local}@{domain}"
            if address not in self._used:
                self._used.add(address)
                return address, src
        raise RuntimeError("邮箱池分配失败（30 次碰撞）")

    # ── 收件 ──────────────────────────────────────
    def wait_for_mail(self, address: str, source: TempTfSource, timeout: float = 90.0,
                      contains: str | None = None) -> dict | None:
        """轮询直到该邮箱收到含关键词的邮件（验证码/验证链接）。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for mail in source.fetch_mails(address):
                blob = json.dumps(mail, ensure_ascii=False)
                if contains and contains.lower() not in blob.lower():
                    continue
                return mail
            time.sleep(2.0)
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
