"""MailTmSource — mail.tm REST API 邮箱源（P2-4 v7.3 自 email_pool.py 拆分）。"""

from __future__ import annotations

import random
import string
import time

import httpx

from .. import config
from .base import BaseMailSource, log


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
                # 上游可能返回 list（API 变更）或 dict（hydra:member/domains），两种都兼容
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = data.get("hydra:member") or data.get("domains") or []
                else:
                    items = []
                domains = [
                    d.get("domain") for d in items
                    if isinstance(d, dict) and d.get("domain") and d.get("isActive", True)
                ]
                if domains:
                    self._cached_domains = domains
                    self._domains_fetched_at = now
                    return self._cached_domains
        except Exception as e:
            log.warning("mail.tm 获取可用域名失败: %s", e)
        # 默认备选域名
        return self._cached_domains or ["mailtm.me", "sharklasers.com"]

    async def new_address(self) -> tuple[str, dict]:
        # 仅使用实时拉取的域名；过期默认域名（sharklasers 等）已被 mail.tm 拒绝（422），
        # 故不再回退到硬编码旧域名。
        await self._get_domains()
        now = time.time()
        if not self._cached_domains or (now - self._domains_fetched_at >= 3600):
            raise RuntimeError("mail.tm 无法获取有效域名列表")
        domain = random.choice(self._cached_domains)
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
                            det_resp = await self.session.get(f"{self.BASE}/messages/{mid}", headers=headers)
                            if det_resp.status_code == 200:
                                d = det_resp.json()
                                html_list = d.get("html") or []
                                html_content = (
                                    html_list[0] if isinstance(html_list, list) and html_list else str(html_list)
                                )
                                text_content = d.get("text") or d.get("intro") or ""
                                out.append(
                                    {
                                        "id": mid,
                                        "from": (d.get("from") or {}).get("address", ""),
                                        "subject": d.get("subject", ""),
                                        "bodyHtml": html_content or text_content,
                                        "bodyPreview": text_content or html_content,
                                    }
                                )
                                continue
                        except Exception:
                            pass
                    out.append(
                        {
                            "id": mid or "",
                            "from": (item.get("from") or {}).get("address", ""),
                            "subject": item.get("subject", ""),
                            "bodyHtml": item.get("intro", ""),
                            "bodyPreview": item.get("intro", ""),
                        }
                    )
                return out
        except Exception as e:
            log.warning("mail.tm 收件失败 %s: %s", address, e)
        return []
