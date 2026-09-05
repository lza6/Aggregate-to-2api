"""CustomImapSource — 自建域名通配符邮箱 / IMAP 收件源（P2-4 v7.3 自 email_pool.py 拆分）。"""

from __future__ import annotations

import asyncio
import email
import os
import random
import string
from email.header import decode_header

from .base import BaseMailSource, log


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
        self.use_ssl = (
            use_ssl if os.getenv("IF_IMAP_SSL") is None else (os.getenv("IF_IMAP_SSL", "1") in ("1", "true", "True"))
        )

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
                if (
                    address.lower() not in to_hdr.lower()
                    and address.lower() not in str(msg.get("Delivered-To", "")).lower()
                ):
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

                mails.append(
                    {
                        "id": mid.decode("utf-8", errors="ignore") if isinstance(mid, bytes) else str(mid),
                        "from": str(msg.get("From", "")),
                        "to": to_hdr,
                        "subject": decoded_subj,
                        "bodyHtml": body_html or body_text,
                        "bodyPreview": body_text or body_html,
                    }
                )
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
