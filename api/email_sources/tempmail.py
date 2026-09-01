"""TempMailSource — temp-mail.org web2 API 邮箱源（P2-4 v7.3 自 email_pool.py 拆分）。

建箱限速常量 EMAIL_CREATE_MIN_INTERVAL / EMAIL_CREATE_BACKOFF 定义在
email_sources/_limits.py（叶子模块，无循环 import）。
"""

from __future__ import annotations

import asyncio
import time

import httpx

from ._limits import EMAIL_CREATE_BACKOFF, EMAIL_CREATE_MIN_INTERVAL
from .base import BaseMailSource, log


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
                                out.append(
                                    {
                                        "id": str(mid),
                                        "subject": ddata.get("subject") or item.get("subject", ""),
                                        "bodyHtml": ddata.get("bodyHtml") or ddata.get("bodyText") or "",
                                        "bodyPreview": ddata.get("bodyPreview") or item.get("bodyPreview", ""),
                                    }
                                )
                                continue
                        except Exception:
                            pass
                    out.append(item)
                return out
        except Exception as e:
            log.warning("temp-mail 收件失败 %s: %s", address, e)
        return []
