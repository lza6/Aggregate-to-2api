"""LinshiMailSource — linshi-email.com 免费临时邮箱源（P2-4 v7.3 自 email_pool.py 拆分）。"""

from __future__ import annotations

import hashlib
import os
import random
import string
import time

import httpx

from .. import config
from .base import BaseMailSource, log


# ── 1. LinshiMailSource (自建/现有免费临时邮箱，零 429) ───
class LinshiMailSource(BaseMailSource):
    """linshi-email.com 免费临时邮箱源，本地生成地址，零 429 限流。

    注意：默认域名已大多被 nanobanana-pro.com 拉黑（INVALID_EMAIL 400），
    因此此源 priority 调低；仅当其它源不可用时兜底。可通过
    IF_LINSHI_DOMAINS 覆盖域名列表。
    """

    name = "linshi-email"
    BASE = "https://www.linshi-email.com"
    DOMAINS = [
        d.strip()
        for d in os.getenv("IF_LINSHI_DOMAINS", "iwatermail.com,fextemp.com,boximail.com,chitthi.in").split(",")
        if d.strip()
    ]

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
                        out.append(
                            {
                                "id": m.get("id", ""),
                                "from": m.get("from", ""),
                                "subject": m.get("subject", ""),
                                "bodyHtml": content,
                                "bodyPreview": content,
                            }
                        )
                    return out
                elif isinstance(data, list):
                    return data
        except Exception as e:
            log.warning("linshi-email 收件失败 %s: %s", address, e)
        return []


# 兼容导入与别名
LinshiEmailSource = LinshiMailSource
