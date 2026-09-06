"""AccountPool CRUD mixin：账号读写/分页/积分扣减/状态标记（P0-F2 拆分）。

从 pool.py 拆出的读写兼容接口：add/list/list_page/get/update_credits/
consume_credits/mark。方法签名/SQL/列名全部不变，仅物理位置迁移到本 mixin。
"""

from __future__ import annotations

import time


class StoreMixin:
    """账号 CRUD 读写 mixin，由 AccountPool 多继承组合。"""

    # ── 读写兼容接口（全 async）──────────────────────────────

    async def add(
        self,
        provider: str,
        email: str,
        cookie: str,
        password: str | None = None,
        credits: int = 0,
        status: str = "ok",
        note: str = "",
        register_ip: str = "",
    ) -> None:
        now = time.time()
        if cookie == "mock-session":
            note = (note + " mock").strip()
        conn = await self._ensure_conn()
        async with self._lock:
            await conn.execute(
                "INSERT OR REPLACE INTO accounts (provider,email,password,cookie,credits,status,created_at,updated_at,note,cooling_since,borrowed_at,register_ip)"
                " VALUES (?,?,?,?,?,?,?,?,?,NULL,NULL,?)",
                (provider, email, password, cookie, credits, status, now, now, note, register_ip),
            )
            await conn.commit()

    async def list(self, provider: str | None = None, status: str | None = None) -> list[dict]:
        conn = await self._ensure_conn()
        q, args = "SELECT * FROM accounts", []
        conds: list[str] = []
        if provider:
            conds.append("provider=?")
            args.append(provider)
        if status:
            if status in ("ok", "active"):
                conds.append("status IN ('ok', 'active')")
            elif status in ("exhausted", "cooling"):
                conds.append("status IN ('exhausted', 'cooling')")
            elif status in ("banned", "dead"):
                conds.append("status IN ('banned', 'dead')")
            else:
                conds.append("status=?")
                args.append(status)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        async with self._lock:
            cur = await conn.execute(q + " ORDER BY created_at DESC", args)
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_page(
        self,
        provider: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
        search: str = "",
    ) -> dict:
        """分页读取账号列表，避免百万级号池一次性加载到内存。"""
        page = max(1, int(page))
        page_size = min(100, max(1, int(page_size)))
        conds: list[str] = []
        args: list[object] = []
        if provider:
            conds.append("provider=?")
            args.append(provider)
        if status:
            if status in ("ok", "active"):
                conds.append("status IN ('ok', 'active')")
            elif status in ("exhausted", "cooling"):
                conds.append("status IN ('exhausted', 'cooling')")
            elif status in ("banned", "dead"):
                conds.append("status IN ('banned', 'dead')")
            else:
                conds.append("status=?")
                args.append(status)
        if search:
            conds.append("(email LIKE ? OR status LIKE ? OR register_ip LIKE ?)")
            needle = f"%{search.strip()}%"
            args.extend([needle, needle, needle])
        where = f" WHERE {' AND '.join(conds)}" if conds else ""
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(f"SELECT COUNT(*) FROM accounts{where}", args)
            total_row = await cur.fetchone()
            total = total_row[0] if total_row else 0
            offset = (page - 1) * page_size
            cur = await conn.execute(
                f"SELECT * FROM accounts{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*args, page_size, offset],
            )
            rows = await cur.fetchall()
        return {
            "items": [dict(r) for r in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (int(total) + page_size - 1) // page_size),
        }

    async def get(self, provider: str) -> list[dict]:
        """某提供商当前就绪可用账号（含 cookie，供 Provider 用）。"""
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT * FROM accounts WHERE provider=? AND status IN ('ok', 'active') ORDER BY created_at DESC",
                (provider,),
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def update_credits(self, provider: str, email: str, credits: int) -> None:
        conn = await self._ensure_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE accounts SET credits=?, updated_at=? WHERE provider=? AND email=?",
                (credits, time.time(), provider, email),
            )
            await conn.commit()

    async def consume_credits(self, provider: str, email: str, amount: int) -> None:
        """v6.5.1: 生成成功扣减该账号积分，并累计「消耗积分」画像（images_used / credits_used_total）。

        - credits：剩余可用积分（扣减后，下限 0）
        - credits_used_total：该账号累计消耗积分（自增 amount）
        - images_used：该账号累计出图次数（自增 1）
        - last_used_at：最近一次出图时间
        """
        if amount <= 0:
            return
        conn = await self._ensure_conn()
        now = time.time()
        async with self._lock:
            await conn.execute(
                "UPDATE accounts SET credits=MAX(0, credits-?),"
                " credits_used_total=COALESCE(credits_used_total,0)+?,"
                " images_used=COALESCE(images_used,0)+1,"
                " last_used_at=?, updated_at=?"
                " WHERE provider=? AND email=?",
                (amount, amount, now, now, provider, email),
            )
            await conn.commit()

    async def mark(self, provider: str, email: str, status: str, note: str = "") -> None:
        now = time.time()
        cooling_since = now if status in ("cooling", "exhausted") else None
        conn = await self._ensure_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE accounts SET status=?, note=?, cooling_since=?, updated_at=? WHERE provider=? AND email=?",
                (status, note, cooling_since, now, provider, email),
            )
            await conn.commit()
