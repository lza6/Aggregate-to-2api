"""Do22Source — 22.do 免费临时邮箱源（P2-4 v7.3 自 email_pool.py 拆分）。"""

from __future__ import annotations

import hashlib
import json
import time

import httpx

from .. import config
from .base import BaseMailSource, log


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
                            out.append(
                                {
                                    "id": str(mid),
                                    "subject": item.get("subject", ""),
                                    "bodyHtml": content,
                                    "bodyPreview": content,
                                }
                            )
                        else:
                            out.append(item)
                    except Exception:
                        out.append(item)
                return out
        except Exception as e:
            log.warning("22.do 收件失败 %s: %s", address, e)
        return []
