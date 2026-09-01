"""TempMailIoSource — temp-mail.io 无 key 免费邮箱源（P2-4 v7.3 自 email_pool.py 拆分）。

建箱限速常量定义在 email_sources/_limits.py（叶子模块，无循环 import）。
"""

from __future__ import annotations

import asyncio
import time

import httpx

from ._limits import EMAIL_CREATE_BACKOFF, EMAIL_CREATE_MIN_INTERVAL
from .base import BaseMailSource, log


# ── 7.5 TempMailIoSource (temp-mail.io 无 key 免费源) ──────
class TempMailIoSource(BaseMailSource):
    """temp-mail.io REST API 邮箱源（无 key 免费源）。

    实测可用（浏览器抓包确认）：建箱无需任何 API key，
    域名不被 nanobanana-pro.com 拉黑，验证邮件可正常收取。
    - 建箱 POST /api/v3/email/new → {email, token}
    - 拉信 GET /api/v3/email/{address}/messages（可选 Bearer token）
    建箱复用 EMAIL_CREATE_MIN_INTERVAL 限速（与 TempMailSource 相同的
    _last_create 逻辑），高频建箱自动 sleep 防 429。
    """

    name = "temp-mail.io"
    API = "https://api.internal.temp-mail.io"

    def __init__(self) -> None:
        super().__init__(name=self.name, priority=95)
        self._last_create = 0.0
        self.session = httpx.AsyncClient(
            timeout=20.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Origin": "https://temp-mail.io",
                "Referer": "https://temp-mail.io/",
                "Accept": "application/json, text/plain, */*",
            },
        )

    async def new_address(self) -> tuple[str, dict]:
        now = time.time()
        gap = now - self._last_create
        if gap < EMAIL_CREATE_MIN_INTERVAL:
            await asyncio.sleep(EMAIL_CREATE_MIN_INTERVAL - gap)
        r = await self.session.post(
            f"{self.API}/api/v3/email/new",
            json={"min_name_length": 10, "max_name_length": 10},
            headers={"Content-Type": "application/json"},
        )
        self._last_create = time.time()
        if r.status_code == 429:
            self.mark_failure("temp-mail.io 429 Too Many Requests", backoff_seconds=float(EMAIL_CREATE_BACKOFF))
            raise RuntimeError(f"temp-mail.io 建箱限流(429)，退避 {EMAIL_CREATE_BACKOFF}s")
        if r.status_code != 200:
            raise RuntimeError(f"temp-mail.io 建箱失败 HTTP {r.status_code}: {r.text[:120]}")
        data = r.json()
        address = str(data.get("email") or "")
        token = str(data.get("token") or "")
        if "@" not in address or not token:
            raise RuntimeError(f"temp-mail.io 返回异常: {str(data)[:150]}")
        return address, {"source": self.name, "token": token}

    async def fetch_mails(self, address: str, state: dict | None = None) -> list[dict]:
        token = (state or {}).get("token")
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            r = await self.session.get(
                f"{self.API}/api/v3/email/{address}/messages",
                headers=headers,
            )
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else []
                out = []
                for item in items:
                    frm = item.get("from") or {}
                    from_addr = frm.get("address") if isinstance(frm, dict) else str(frm)
                    body_html = item.get("body_html") or item.get("bodyHtml") or ""
                    body_text = item.get("body_text") or item.get("bodyText") or ""
                    body_preview = item.get("intro") or body_text or body_html
                    out.append(
                        {
                            "id": str(item.get("id") or ""),
                            "from": from_addr,
                            "subject": item.get("subject", ""),
                            "bodyHtml": body_html or body_text,
                            "bodyPreview": body_preview,
                        }
                    )
                return out
        except Exception as e:
            log.warning("temp-mail.io 收件失败 %s: %s", address, e)
        return []
