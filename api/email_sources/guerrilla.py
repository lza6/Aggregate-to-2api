"""GuerrillaMailSource — GuerrillaMail 免认证临时邮箱源（P2-4 v7.3 自 email_pool.py 拆分）。"""

from __future__ import annotations

import httpx

from .. import config
from .base import BaseMailSource, log


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
                    out.append(
                        {
                            "id": str(mid or ""),
                            "from": item.get("mail_from", ""),
                            "subject": item.get("mail_subject", ""),
                            "bodyHtml": body,
                            "bodyPreview": item.get("mail_excerpt") or body,
                        }
                    )
                return out
        except Exception as e:
            log.warning("GuerrillaMail 收件失败 %s: %s", address, e)
        return []
