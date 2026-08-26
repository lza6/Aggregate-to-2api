"""邮箱池：多源弹性邮箱提供商适配器 (Mail Provider Strategy) + 注册记录。

支持多源临时与自建邮箱提供商：
1. LinshiMailSource (linshi-email.com 免费临时邮箱，零 429，极速)
2. MailTmSource (mail.tm REST API，速度快且稳定，支持动态创建 account 并基于 JWT 拉取 messages)
3. GuerrillaMailSource (GuerrillaMail 免认证公共/私有临时邮箱与邮件抓取)
4. CustomImapSource (自建域名邮箱通配符捕捉，支持通过 IMAP4/IMAP4_SSL 异步非阻塞读取)
5. Do22Source (22.do 免费临时邮箱，REST 全链路)
6. TempMailSource (temp-mail.org web2 API)
7. TempTfSource (temp.tf 十几亿级随机邮箱)

核心职责：
- 提供规范统一的 BaseMailSource 适配器接口与自动退避/打分/健康度管理。
- 为自动注册分配「未使用过」的邮箱，按优先级、可用性评分与风控状态自适应轮换。
- 某邮箱源遭遇 429 或故障时自动退避并平滑切换到备用源。
- 轮询收件：验证码/验证链接精准提取。
- 持久化邮箱与域名注册记录到 SQLite，重启不丢。
"""
from __future__ import annotations

import asyncio
import email
from email.header import decode_header
import hashlib
import json
import logging
import os
import random
import sqlite3
import string
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from . import config

log = logging.getLogger("email_pool")

DB_FILE = os.getenv("IF_EMAIL_DB_FILE", "data/email_registry.db")
# temp-mail 建箱最小间隔（秒）：防 429 限流
EMAIL_CREATE_MIN_INTERVAL = int(os.getenv("IF_EMAIL_CREATE_INTERVAL", "30"))
EMAIL_CREATE_BACKOFF = int(os.getenv("IF_EMAIL_CREATE_BACKOFF", "60"))


# ── 规范基类 ──────────────────────────────────────────
@dataclass
class BaseMailSource:
    """统一邮箱源抽象基类。"""

    name: str
    session: httpx.AsyncClient | None = field(default=None, repr=False)
    priority: int = 50
    cooldown_until: float = 0.0
    failure_count: int = 0
    success_count: int = 0
    last_error: str | None = None

    async def new_address(self) -> tuple[str, dict]:
        """生成一个新邮箱，返回 (address, state)。state 供收件用。"""
        raise NotImplementedError

    async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
        """取该邮箱收到的邮件列表。"""
        raise NotImplementedError

    def is_available(self) -> bool:
        """检查当前邮箱源是否处于可用状态（未在冷却期）。"""
        return time.time() >= self.cooldown_until

    def mark_success(self) -> None:
        """记录一次成功分配或收件。"""
        self.success_count += 1
        self.failure_count = max(0, self.failure_count - 1)
        self.last_error = None

    def mark_failure(self, error: str = "", backoff_seconds: float = 30.0) -> None:
        """记录一次失败，并按指数退避冷却。"""
        self.failure_count += 1
        self.last_error = str(error)
        # 1.5 倍指数退避，最大 600s
        multiplier = 1.5 ** min(self.failure_count - 1, 5)
        backoff = min(backoff_seconds * multiplier, 600.0)
        self.cooldown_until = time.time() + backoff
        log.warning(
            "邮箱源 [%s] 发生故障 (累计 %d 次)，退避 %.1fs: %s",
            self.name,
            self.failure_count,
            backoff,
            error,
        )

    def score(self) -> float:
        """根据优先级、成功率与健康度综合打分。"""
        if not self.is_available():
            # 冷却中扣除大量分数
            return -100.0 + (self.priority * 0.1)
        total = self.success_count + self.failure_count
        rate = (self.success_count + 1) / (total + 2)  # 拉普拉斯平滑
        return (self.priority * 10.0) + (rate * 50.0) - (self.failure_count * 10.0)


# 向后兼容别名
MailSource = BaseMailSource


# ── 1. LinshiMailSource (自建/现有免费临时邮箱，零 429) ───
class LinshiMailSource(BaseMailSource):
    """linshi-email.com 免费临时邮箱源，本地生成地址，零 429 限流。

    注意：默认域名已大多被 nanobanana-pro.com 拉黑（INVALID_EMAIL 400），
    因此此源 priority 调低；仅当其它源不可用时兜底。可通过
    IF_LINSHI_DOMAINS 覆盖域名列表。
    """

    name = "linshi-email"
    BASE = "https://www.linshi-email.com"
    DOMAINS = [d.strip() for d in os.getenv("IF_LINSHI_DOMAINS",
              "iwatermail.com,fextemp.com,boximail.com,chitthi.in").split(",") if d.strip()]

    def __init__(self) -> None:
        # 默认域名被上游拉黑 → 权重降到 10 使其极少被选中；可用域名补齐后靠环境变量覆盖
        super().__init__(name=self.name, priority=10)
        self.session = httpx.AsyncClient(
            timeout=15.0,
            headers={
                "User-Agent": config.USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Origin": self.BASE,
                "Referer": f"{self.BASE}/",
            },
        )

    async def new_address(self) -> tuple[str, dict]:
        local = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        domain = random.choice(self.DOMAINS)
        address = f"{local}@{domain}"
        h = hashlib.md5(address.encode("utf-8")).hexdigest()
        return address, {"source": self.name, "email": address, "hash": h}

    async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
        h = (state or {}).get("hash")
        if not h:
            h = hashlib.md5(address.encode("utf-8")).hexdigest()
        t = int(time.time() * 1000)
        url = f"{self.BASE}/api/v1/refreshmessage/{h}/{address}?t={t}"
        try:
            r = await self.session.get(url)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    msgs = data.get("data") or []
                    out = []
                    for m in msgs:
                        content = m.get("content") or ""
                        out.append({
                            "id": m.get("id", ""),
                            "from": m.get("from", ""),
                            "subject": m.get("subject", ""),
                            "bodyHtml": content,
                            "bodyPreview": content,
                        })
                    return out
                elif isinstance(data, list):
                    return data
        except Exception as e:
            log.warning("linshi-email 收件失败 %s: %s", address, e)
        return []


# 兼容导入与别名
LinshiEmailSource = LinshiMailSource


# ── 2. MailTmSource (mail.tm REST API) ────────────────
class MailTmSource(BaseMailSource):
    """mail.tm 现代临时邮箱源。

    支持动态拉取可注册域名，注册 account 并拿 JWT 鉴权拉取 messages。
    """

    name = "mail.tm"
    BASE = "https://api.mail.tm"

    def __init__(self) -> None:
        super().__init__(name=self.name, priority=80)
        self.session = httpx.AsyncClient(
            timeout=20.0,
            headers={
                "User-Agent": config.USER_AGENT,
                "Accept": "application/json",
            },
        )
        self._cached_domains: list[str] = []
        self._domains_fetched_at: float = 0.0

    async def _get_domains(self) -> list[str]:
        now = time.time()
        if self._cached_domains and (now - self._domains_fetched_at < 3600):
            return self._cached_domains
        try:
            r = await self.session.get(f"{self.BASE}/domains?page=1")
            if r.status_code == 200:
                data = r.json()
                items = data.get("hydra:member") or data.get("domains") or []
                domains = [d.get("domain") for d in items if d.get("domain") and d.get("isActive", True)]
                if domains:
                    self._cached_domains = domains
                    self._domains_fetched_at = now
                    return self._cached_domains
        except Exception as e:
            log.warning("mail.tm 获取可用域名失败: %s", e)
        # 默认备选域名
        return self._cached_domains or ["mailtm.me", "sharklasers.com"]

    async def new_address(self) -> tuple[str, dict]:
        domains = await self._get_domains()
        if not domains:
            raise RuntimeError("mail.tm 无可用域名")
        domain = random.choice(domains)
        local = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        address = f"{local}@{domain}"
        password = "".join(random.choices(string.ascii_letters + string.digits, k=12))

        # 1) 创建 account
        create_resp = await self.session.post(
            f"{self.BASE}/accounts",
            json={"address": address, "password": password},
        )
        if create_resp.status_code not in (200, 201):
            if create_resp.status_code == 429:
                self.mark_failure("mail.tm 429 Too Many Requests", backoff_seconds=60.0)
            raise RuntimeError(f"mail.tm 创建账号失败 HTTP {create_resp.status_code}: {create_resp.text[:120]}")

        # 2) 登录获取 JWT Token
        token_resp = await self.session.post(
            f"{self.BASE}/token",
            json={"address": address, "password": password},
        )
        if token_resp.status_code != 200:
            raise RuntimeError(f"mail.tm 获取 Token 失败 HTTP {token_resp.status_code}: {token_resp.text[:120]}")
        token = (token_resp.json() or {}).get("token") or ""
        if not token:
            raise RuntimeError("mail.tm 返回空 JWT Token")

        return address, {
            "source": self.name,
            "email": address,
            "password": password,
            "token": token,
        }

    async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
        token = (state or {}).get("token")
        if not token:
            return []
        headers = {"Authorization": f"Bearer {token}"}
        try:
            r = await self.session.get(f"{self.BASE}/messages", headers=headers)
            if r.status_code == 200:
                data = r.json()
                items = data.get("hydra:member") or data.get("messages") or []
                out = []
                for item in items:
                    mid = item.get("id") or item.get("_id")
                    if mid:
                        try:
                            det_resp = await self.session.get(
                                f"{self.BASE}/messages/{mid}", headers=headers
                            )
                            if det_resp.status_code == 200:
                                d = det_resp.json()
                                html_list = d.get("html") or []
                                html_content = html_list[0] if isinstance(html_list, list) and html_list else str(html_list)
                                text_content = d.get("text") or d.get("intro") or ""
                                out.append({
                                    "id": mid,
                                    "from": (d.get("from") or {}).get("address", ""),
                                    "subject": d.get("subject", ""),
                                    "bodyHtml": html_content or text_content,
                                    "bodyPreview": text_content or html_content,
                                })
                                continue
                        except Exception:
                            pass
                    out.append({
                        "id": mid or "",
                        "from": (item.get("from") or {}).get("address", ""),
                        "subject": item.get("subject", ""),
                        "bodyHtml": item.get("intro", ""),
                        "bodyPreview": item.get("intro", ""),
                    })
                return out
        except Exception as e:
            log.warning("mail.tm 收件失败 %s: %s", address, e)
        return []


# ── 3. GuerrillaMailSource (GuerrillaMail 免认证临时邮箱) ───
class GuerrillaMailSource(BaseMailSource):
    """GuerrillaMail 开放式临时邮箱源。"""

    name = "guerrillamail"
    BASE = "https://api.guerrillamail.com/ajax.php"

    def __init__(self) -> None:
        super().__init__(name=self.name, priority=75)
        self.session = httpx.AsyncClient(
            timeout=15.0,
            headers={
                "User-Agent": config.USER_AGENT,
                "Accept": "application/json",
            },
        )

    async def new_address(self) -> tuple[str, dict]:
        try:
            r = await self.session.get(
                self.BASE,
                params={"f": "get_email_address", "lang": "en"},
            )
            if r.status_code == 200:
                data = r.json()
                address = data.get("email_addr") or ""
                sid_token = data.get("sid_token") or ""
                if "@" in address and sid_token:
                    return address, {
                        "source": self.name,
                        "email": address,
                        "sid_token": sid_token,
                    }
            if r.status_code == 429:
                self.mark_failure("GuerrillaMail 429 Rate Limit", backoff_seconds=60.0)
            raise RuntimeError(f"GuerrillaMail 建箱失败 HTTP {r.status_code}: {r.text[:120]}")
        except Exception as e:
            raise RuntimeError(f"GuerrillaMail 生成邮箱异常: {e}")

    async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
        sid_token = (state or {}).get("sid_token")
        if not sid_token:
            return []
        try:
            r = await self.session.get(
                self.BASE,
                params={"f": "check_email", "seq": "0", "sid_token": sid_token},
            )
            if r.status_code == 200:
                data = r.json()
                items = data.get("list") or []
                out = []
                for item in items:
                    mid = item.get("mail_id")
                    body = item.get("mail_body") or item.get("mail_excerpt") or ""
                    if mid and (not body or len(body) < 30):
                        try:
                            det_resp = await self.session.get(
                                self.BASE,
                                params={"f": "fetch_email", "email_id": mid, "sid_token": sid_token},
                            )
                            if det_resp.status_code == 200:
                                d = det_resp.json()
                                body = d.get("mail_body") or body
                        except Exception:
                            pass
                    out.append({
                        "id": str(mid or ""),
                        "from": item.get("mail_from", ""),
                        "subject": item.get("mail_subject", ""),
                        "bodyHtml": body,
                        "bodyPreview": item.get("mail_excerpt") or body,
                    })
                return out
        except Exception as e:
            log.warning("GuerrillaMail 收件失败 %s: %s", address, e)
        return []


# ── 4. CustomImapSource (自建域名通配符邮箱 / IMAP 收件) ───
class CustomImapSource(BaseMailSource):
    """自建域名通配符捕捉邮箱源。

    配合 Cloudflare Email Routing 或邮件服务器 Catch-all 通配符转发：
    - 本地可任意随机生成 `*@yourdomain.com` 邮箱。
    - 收件通过标准 IMAP 协议（异步线程池封装 `imaplib.IMAP4_SSL` / `imaplib.IMAP4`）登录拉取。
    """

    name = "custom-imap"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        domain: str | None = None,
        use_ssl: bool = True,
    ) -> None:
        self.host = host or os.getenv("IF_IMAP_HOST", "")
        self.port = int(port or os.getenv("IF_IMAP_PORT", "993"))
        self.username = username or os.getenv("IF_IMAP_USER", "")
        self.password = password or os.getenv("IF_IMAP_PASS", "")
        self.domain = (domain or os.getenv("IF_IMAP_DOMAIN", "")).lstrip("@")
        self.use_ssl = use_ssl if os.getenv("IF_IMAP_SSL") is None else (os.getenv("IF_IMAP_SSL", "1") in ("1", "true", "True"))

        # 如果配置了自建 IMAP 则具有最高优先级，否则不默认启用
        configured = bool(self.host and self.username and self.password and self.domain)
        priority = 95 if configured else 0
        super().__init__(name=self.name, priority=priority)

    def is_configured(self) -> bool:
        return bool(self.host and self.username and self.password and self.domain)

    def is_available(self) -> bool:
        return self.is_configured() and super().is_available()

    async def new_address(self) -> tuple[str, dict]:
        if not self.is_configured():
            raise RuntimeError("CustomImapSource 未配置 IMAP 环境变量 (IF_IMAP_HOST/USER/PASS/DOMAIN)")
        local = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        address = f"{local}@{self.domain}"
        return address, {"source": self.name, "email": address}

    def _sync_fetch_mails(self, address: str) -> list[dict]:
        import imaplib

        mails: list[dict] = []
        client: imaplib.IMAP4 | None = None
        try:
            if self.use_ssl:
                client = imaplib.IMAP4_SSL(self.host, self.port, timeout=15)
            else:
                client = imaplib.IMAP4(self.host, self.port, timeout=15)
            client.login(self.username, self.password)
            client.select("INBOX", readonly=True)

            # 搜索匹配 TO 或 HEADER TO 包含该地址的邮件
            status, data = client.search(None, f'HEADER TO "{address}"')
            if status != "OK" or not data or not data[0]:
                status, data = client.search(None, f'TO "{address}"')
            if status != "OK" or not data or not data[0]:
                # 兼容性搜索：拉取最近 10 封做本地过滤
                status, data = client.search(None, "ALL")

            msg_ids = (data[0].split() if (data and data[0]) else [])[-10:]
            for mid in reversed(msg_ids):
                res, fetch_data = client.fetch(mid, "(RFC822)")
                if res != "OK" or not fetch_data:
                    continue
                raw_email = fetch_data[0][1]
                msg = email.message_from_bytes(raw_email)

                # 提取 Header
                to_hdr = str(msg.get("To", ""))
                if address.lower() not in to_hdr.lower() and address.lower() not in str(msg.get("Delivered-To", "")).lower():
                    continue

                # 解码 Subject
                raw_subj = msg.get("Subject", "")
                decoded_subj = ""
                for part, enc in decode_header(raw_subj):
                    if isinstance(part, bytes):
                        decoded_subj += part.decode(enc or "utf-8", errors="ignore")
                    else:
                        decoded_subj += str(part)

                # 提取正文
                body_html = ""
                body_text = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ctype = part.get_content_type()
                        payload = part.get_payload(decode=True)
                        if not payload:
                            continue
                        charset = part.get_content_charset() or "utf-8"
                        text = payload.decode(charset, errors="ignore")
                        if ctype == "text/html":
                            body_html = text
                        elif ctype == "text/plain":
                            body_text = text
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        charset = msg.get_content_charset() or "utf-8"
                        text = payload.decode(charset, errors="ignore")
                        if msg.get_content_type() == "text/html":
                            body_html = text
                        else:
                            body_text = text

                mails.append({
                    "id": mid.decode("utf-8", errors="ignore") if isinstance(mid, bytes) else str(mid),
                    "from": str(msg.get("From", "")),
                    "to": to_hdr,
                    "subject": decoded_subj,
                    "bodyHtml": body_html or body_text,
                    "bodyPreview": body_text or body_html,
                })
        except Exception as e:
            log.warning("IMAP 同步拉取邮件失败 %s: %s", address, e)
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
                try:
                    client.logout()
                except Exception:
                    pass
        return mails

    async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
        if not self.is_configured():
            return []
        return await asyncio.to_thread(self._sync_fetch_mails, address)


# ── 5. Do22Source (22.do 免费临时邮箱) ────────────────
class Do22Source(BaseMailSource):
    """22.do 免费临时邮箱（REST 全链路，实测可用）。"""

    name = "22.do"
    BASE = "https://22.do"

    def __init__(self) -> None:
        super().__init__(name=self.name, priority=75)
        self.session = httpx.AsyncClient(
            timeout=15.0,
            headers={
                "User-Agent": config.USER_AGENT,
                "Content-Type": "application/json",
                "Origin": self.BASE,
                "Referer": f"{self.BASE}/",
                "Accept": "*/*",
            },
        )

    async def new_address(self) -> tuple[str, dict]:
        address = ""
        allowed = ("@tnbeta.com", "@colaname.com", "@colabeta.com", "@usdtbeta.com")
        for _ in range(15):
            r = await self.session.post(f"{self.BASE}/action/mailbox/create", json={"type": "random"})
            if r.status_code != 200:
                continue
            data = (r.json() or {}).get("data") or {}
            em = str(data.get("email") or "")
            if em and any(em.endswith(suf) for suf in allowed):
                address = em
                break
        if not address or "@" not in address:
            raise RuntimeError("22.do 无法创建白名单域名邮箱")

        await self.session.post(
            f"{self.BASE}/action/mailbox/login",
            json={"email": address, "language": "en-US"},
        )
        uuid_hex = hashlib.md5(f"22do_{address}_{time.time()}".encode()).hexdigest()
        token_resp = await self.session.post(
            f"{self.BASE}/action/mailbox/applyToken",
            json={"email": address, "uuid": uuid_hex},
        )
        token = ((token_resp.json() or {}).get("data") or {}).get("token") or ""
        return address, {"source": self.name, "email": address, "token": token}

    async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
        email_addr = (state or {}).get("email") or address
        token = (state or {}).get("token")
        if not token:
            return []
        try:
            r = await self.session.post(
                f"{self.BASE}/action/mailbox/message",
                json={"email": email_addr, "lastime": 0},
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code == 200:
                raw_data = (r.json() or {}).get("data")
                if not raw_data or not isinstance(raw_data, list):
                    return []
                out = []
                for item in raw_data:
                    mid = item.get("id") or item.get("messageId")
                    if not mid:
                        out.append(item)
                        continue
                    try:
                        det = await self.session.post(
                            f"{self.BASE}/action/mailbox/messageDetail",
                            json={"email": email_addr, "id": mid},
                            headers={"Authorization": f"Bearer {token}"},
                        )
                        if det.status_code == 200:
                            det_data = (det.json() or {}).get("data") or {}
                            content = det_data.get("content") or det_data.get("html") or json.dumps(det_data)
                            out.append({
                                "id": str(mid),
                                "subject": item.get("subject", ""),
                                "bodyHtml": content,
                                "bodyPreview": content,
                            })
                        else:
                            out.append(item)
                    except Exception:
                        out.append(item)
                return out
        except Exception as e:
            log.warning("22.do 收件失败 %s: %s", address, e)
        return []


# ── 6. TempMailSource (temp-mail.org web2 API) ────────
class TempMailSource(BaseMailSource):
    """temp-mail.org 收件源（web2.temp-mail.org）。

    实测验证（抓包确认）：temp-mail.org 的 hutdot.com 等域名在
    nanobanana-pro.com 注册有效（验证邮件可正常收取），
    因此此源 priority 提升为最高档。
    """

    name = "temp-mail"
    API = "https://web2.temp-mail.org"

    def __init__(self) -> None:
        super().__init__(name=self.name, priority=95)
        self._last_create = 0.0
        self.session = httpx.AsyncClient(
            timeout=20.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Origin": "https://temp-mail.org",
                "Referer": "https://temp-mail.org/",
                "Accept": "application/json, text/plain, */*",
            },
        )

    async def new_address(self) -> tuple[str, dict]:
        now = time.time()
        gap = now - self._last_create
        if gap < EMAIL_CREATE_MIN_INTERVAL:
            await asyncio.sleep(EMAIL_CREATE_MIN_INTERVAL - gap)
        r = await self.session.post(
            f"{self.API}/mailbox",
            json={},
            headers={"Content-Type": "application/json"},
        )
        self._last_create = time.time()
        if r.status_code == 429:
            self.mark_failure("temp-mail 429 Too Many Requests", backoff_seconds=float(EMAIL_CREATE_BACKOFF))
            raise RuntimeError(f"temp-mail 建箱限流(429)，退避 {EMAIL_CREATE_BACKOFF}s")
        if r.status_code != 200:
            raise RuntimeError(f"temp-mail 建箱失败 HTTP {r.status_code}")
        data = r.json()
        address = str(data.get("mailbox") or "")
        token = str(data.get("token") or "")
        if "@" not in address or not token:
            raise RuntimeError(f"temp-mail 返回异常: {str(data)[:150]}")
        return address, {"source": self.name, "token": token}

    async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
        token = (state or {}).get("token")
        if not token:
            return []
        try:
            r = await self.session.get(
                f"{self.API}/messages",
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code == 200:
                raw_msgs = r.json()
                items = []
                if isinstance(raw_msgs, list):
                    items = raw_msgs
                elif isinstance(raw_msgs, dict):
                    for k in ("messages", "data", "mailbox"):
                        v = raw_msgs.get(k)
                        if isinstance(v, list):
                            items = v
                            break
                out = []
                for item in items:
                    mid = item.get("_id") or item.get("id")
                    if mid:
                        try:
                            det = await self.session.get(
                                f"{self.API}/messages/{mid}",
                                headers={"Authorization": f"Bearer {token}"},
                            )
                            if det.status_code == 200:
                                ddata = det.json()
                                out.append({
                                    "id": str(mid),
                                    "subject": ddata.get("subject") or item.get("subject", ""),
                                    "bodyHtml": ddata.get("bodyHtml") or ddata.get("bodyText") or "",
                                    "bodyPreview": ddata.get("bodyPreview") or item.get("bodyPreview", ""),
                                })
                                continue
                        except Exception:
                            pass
                    out.append(item)
                return out
        except Exception as e:
            log.warning("temp-mail 收件失败 %s: %s", address, e)
        return []


# ── 7. TempTfSource (temp.tf 十几亿级随机邮箱) ──────────
class TempTfSource(BaseMailSource):
    """temp.tf 邮箱源（本地生成，空间大，兜底）。"""

    name = "temp.tf"
    _domains = ["high.edu.pl", "duck.com", "temp.tf", "jetable.net"]

    def __init__(self) -> None:
        super().__init__(name=self.name, priority=40)
        self.session = httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": config.USER_AGENT},
        )

    async def new_address(self) -> tuple[str, dict]:
        local = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        domain = random.choice(self._domains)
        return f"{local}@{domain}", {"source": self.name, "domain": domain}

    async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
        try:
            r = await self.session.post("https://temp.tf/api/check", json={"email": address})
            if r.status_code == 200:
                return r.json().get("data") or []
        except Exception as e:
            log.warning("temp.tf 收件失败 %s: %s", address, e)
        return []


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
                Do22Source(),
                GuerrillaMailSource(),
                TempMailSource(),
                TempTfSource(),
            ]
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # 极限性能调优参数（v5.2）：与主库一致的写读无锁并发 + 内存缓存
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._conn.execute("PRAGMA cache_size=-64000")      # 64MB
        self._conn.execute("PRAGMA mmap_size=268435456")    # 256MB
        self._conn.execute("PRAGMA temp_store=MEMORY")
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

            CREATE TABLE IF NOT EXISTS domain_risk (
                domain      TEXT PRIMARY KEY,
                fail_count  INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                status      TEXT DEFAULT 'ok',
                last_updated REAL
            );
            """)
            self._conn.commit()

    def _load_used(self) -> set[str]:
        rows = self._conn.execute("SELECT email FROM email_registry").fetchall()
        return {r["email"] for r in rows}

    def _find_source(self, name: str) -> BaseMailSource | None:
        canonical = self._ALIASES.get(name.lower().strip(), name.lower().strip())
        for src in self._sources:
            if src.name == canonical or src.name == name:
                return src
        return None

    def risky_domains(self, min_fails: int = 3) -> set[str]:
        """返回失败次数 >= min_fails 的拉黑域名集合（供 allocate 过滤）。"""
        rows = self._conn.execute(
            "SELECT domain FROM domain_risk WHERE fail_count >= ? AND status = 'risky'",
            (min_fails,),
        ).fetchall()
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
        risky = self.risky_domains()  # 已被上游拉黑的域名（连续失败 >=3）
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
        """轮询直到该邮箱收到含指定关键词的邮件（验证码/验证链接）。"""
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
    def record(self, email: str, provider: str, status: str = "ok", note: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO email_registry (email, provider, registered_at, status, note)"
                " VALUES (?, ?, ?, ?, ?)",
                (email, provider, time.time(), status, note),
            )
            domain = email.split("@")[-1] if "@" in email else ""
            if domain:
                if status == "ok":
                    self._conn.execute(
                        """INSERT INTO domain_risk (domain, success_count, last_updated)
                           VALUES (?, 1, ?)
                           ON CONFLICT(domain) DO UPDATE SET
                           success_count = success_count + 1,
                           last_updated = excluded.last_updated""",
                        (domain, time.time()),
                    )
                else:
                    self._conn.execute(
                        """INSERT INTO domain_risk (domain, fail_count, status, last_updated)
                           VALUES (?, 1, 'risky', ?)
                           ON CONFLICT(domain) DO UPDATE SET
                           fail_count = fail_count + 1,
                           last_updated = excluded.last_updated""",
                        (domain, time.time()),
                    )
            self._conn.commit()

    def registered_providers(self, email: str) -> list[str]:
        rows = self._conn.execute("SELECT provider FROM email_registry WHERE email=?", (email,)).fetchall()
        return [r["provider"] for r in rows]

    def stats(self) -> dict:
        total = self._conn.execute("SELECT COUNT(*) FROM email_registry").fetchone()[0]
        by_provider = dict(
            self._conn.execute(
                "SELECT provider, COUNT(*) FROM email_registry GROUP BY provider"
            ).fetchall()
        )
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
            "sources": sources_status,
        }


# 模块级单例
email_pool = EmailPool()
