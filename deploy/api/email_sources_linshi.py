"""linshi-email.com 免费临时邮箱源（chatgpt2api 逆向提取）。

API 契约：
- 建箱：直接本地分配随机邮箱名，如 {random10}@iwatermail.com
- 收件：GET https://www.linshi-email.com/api/v1/refreshmessage/{md5_hash}/{email}?t={timestamp}
  返回 JSON: { "data": [ { "id": "...", "from": "...", "subject": "...", "content": "..." } ] }
"""
from __future__ import annotations

import hashlib
import logging
import random
import time
import httpx
from . import config

log = logging.getLogger("email_pool.linshi")

DOMAINS = [
    "iwatermail.com",
    "fextemp.com",
    "boximail.com",
    "chitthi.in"
]

class LinshiEmailSource:
    name = "linshi-email"
    BASE = "https://www.linshi-email.com"

    def __init__(self) -> None:
        self.session = httpx.AsyncClient(
            timeout=15.0,
            headers={
                "User-Agent": config.USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Origin": self.BASE,
                "Referer": f"{self.BASE}/",
            }
        )

    async def new_address(self) -> tuple[str, dict]:
        local = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=10))
        domain = random.choice(DOMAINS)
        address = f"{local}@{domain}"
        # 生成前端对应的 hash key
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
                    # 归一化字段供提取器识别
                    out = []
                    for m in msgs:
                        out.append({
                            "subject": m.get("subject", ""),
                            "bodyHtml": m.get("content", ""),
                            "bodyPreview": m.get("content", ""),
                        })
                    return out
                elif isinstance(data, list):
                    return data
        except Exception as e:
            log.warning("linshi-email 收件失败 %s: %s", address, e)
        return []
