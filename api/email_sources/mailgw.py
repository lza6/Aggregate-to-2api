"""MailGwSource — api.mail.gw 自建邮箱源（P2-4 v7.3 自 email_pool.py 拆分）。"""

from __future__ import annotations

import random
import string
import time

import httpx

from .base import BaseMailSource, log


# ── 7.6 MailGwSource (api.mail.gw 自建邮箱) ─────────────
class MailGwSource(BaseMailSource):
    """api.mail.gw REST API 邮箱源。

    实测可用（无 key 免费源）：动态拉取可用域名并缓存 1h，
    自建 account 后经 /token 拿 JWT 拉取 messages。
    域名不被 nanobanana-pro.com 拉黑，验证邮件可正常收取。
    - 域名 GET /domains → list[{"domain","isActive"}]（缓存 1h）
    - 建箱 POST /accounts → 201 {id, address}
    - 鉴权 POST /token → {token}
    - 拉信 GET /messages?page=1&itemsPerPage=20（Bearer token），Hydra 风格响应
    """

    name = "mail.gw"
    BASE = "https://api.mail.gw"
    FALLBACK_DOMAINS = ["westcast-systems.com"]

    def __init__(self) -> None:
        super().__init__(name=self.name, priority=75)
        self.session = httpx.AsyncClient(
            timeout=20.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Origin": "https://mail.gw",
                "Referer": "https://mail.gw/",
            },
        )
        self._cached_domains: list[str] = []
        self._domains_fetched_at: float = 0.0

    async def _get_domains(self) -> list[str]:
        now = time.time()
        if self._cached_domains and (now - self._domains_fetched_at < 3600):
            return self._cached_domains
        try:
            r = await self.session.get(f"{self.BASE}/domains")
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("hydra:member") or data.get("domains") or []
                domains = [
                    d.get("domain")
                    for d in items
                    if isinstance(d, dict) and d.get("domain") and d.get("isActive", True)
                ]
                if domains:
                    self._cached_domains = domains
                    self._domains_fetched_at = now
                    return self._cached_domains
        except Exception as e:
            log.warning("mail.gw 获取可用域名失败: %s", e)
        return self._cached_domains or list(self.FALLBACK_DOMAINS)

    async def new_address(self) -> tuple[str, dict]:
        domains = await self._get_domains()
        domain = random.choice(domains)
        local = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        address = f"{local}@{domain}"
        password = "".join(random.choices(string.ascii_letters + string.digits, k=12))

        # 1) 创建 account
        create_resp = await self.session.post(
            f"{self.BASE}/accounts",
            json={"address": address, "password": password},
        )
        if create_resp.status_code == 429:
            self.mark_failure("mail.gw 429 Too Many Requests", backoff_seconds=60.0)
            raise RuntimeError("mail.gw 建箱限流(429)，退避 60s")
        if create_resp.status_code != 201:
            raise RuntimeError(f"mail.gw 创建账号失败 HTTP {create_resp.status_code}: {create_resp.text[:120]}")

        # 2) 获取 Token
        token_resp = await self.session.post(
            f"{self.BASE}/token",
            json={"address": address, "password": password},
        )
        if token_resp.status_code != 200:
            raise RuntimeError(f"mail.gw 获取 Token 失败 HTTP {token_resp.status_code}: {token_resp.text[:120]}")
        token = (token_resp.json() or {}).get("token") or ""
        if not token:
            raise RuntimeError("mail.gw 返回空 Token")

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
            r = await self.session.get(
                f"{self.BASE}/messages",
                params={"page": 1, "itemsPerPage": 20},
                headers=headers,
            )
            if r.status_code == 200:
                data = r.json()
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = data.get("hydra:member") or data.get("messages") or []
                out = []
                for item in items:
                    frm = item.get("from") or {}
                    from_addr = frm.get("address") if isinstance(frm, dict) else str(frm)
                    body_html = item.get("bodyHtml") or item.get("html") or item.get("intro", "")
                    if isinstance(body_html, list):
                        body_html = body_html[0] if body_html else ""
                    body_text = item.get("bodyText") or item.get("text") or item.get("intro", "")
                    if isinstance(body_text, list):
                        body_text = body_text[0] if body_text else ""
                    out.append(
                        {
                            "id": str(item.get("id") or ""),
                            "from": from_addr,
                            "subject": item.get("subject", ""),
                            "bodyHtml": str(body_html or body_text),
                            "bodyPreview": str(body_text or body_html),
                        }
                    )
                return out
        except Exception as e:
            log.warning("mail.gw 收件失败 %s: %s", address, e)
        return []
