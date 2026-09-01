"""TempTfSource — temp.tf 十几亿级随机邮箱源（P2-4 v7.3 自 email_pool.py 拆分）。"""

from __future__ import annotations

import random
import string

import httpx

from .. import config
from .base import BaseMailSource, log


# ── 7.7 TempTfSource (temp.tf 十几亿级随机邮箱) ──────────
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
