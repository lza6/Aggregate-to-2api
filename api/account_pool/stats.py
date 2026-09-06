"""AccountPool 看板/成本/补满画像 mixin（P0-F2 拆分）。

从 pool.py 拆出：counts/total_credits/cost_summary/growth_stats/dashboard。
方法签名/SQL/列名全部不变，仅物理位置迁移到本 mixin。

被 monkeypatch 的常量（TARGET_NANOBANANA）经 `_pkg_attr()` 运行时读包命名空间，
保持 `monkeypatch.setattr("api.account_pool.TARGET_NANOBANANA", ...)` 命中。
"""

from __future__ import annotations

import time

from ._constants import TARGET_NANOBANANA, _pkg_attr


class StatsMixin:
    """看板/成本/补满速率画像 mixin，由 AccountPool 多继承组合。"""

    async def counts(self) -> dict:
        """返回全状态细分统计 (映射为标准 key 与历史 key 兼容)。"""
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute("SELECT provider, status, COUNT(*) c FROM accounts GROUP BY provider, status")
            rows = await cur.fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            p = r["provider"]
            st = r["status"]
            cnt = r["c"]
            prov_dict = out.setdefault(
                p,
                {
                    "active": 0,
                    "ok": 0,
                    "working": 0,
                    "cooling": 0,
                    "exhausted": 0,
                    "dead": 0,
                    "banned": 0,
                    "registering": 0,
                    "unregistered": 0,
                },
            )
            prov_dict[st] = prov_dict.get(st, 0) + cnt
            # 状态别名同步累加
            if st in ("ok", "active"):
                prov_dict["active"] += cnt if st != "active" else 0
                prov_dict["ok"] += cnt if st != "ok" else 0
            elif st in ("cooling", "exhausted"):
                prov_dict["cooling"] += cnt if st != "cooling" else 0
                prov_dict["exhausted"] += cnt if st != "exhausted" else 0
            elif st in ("dead", "banned"):
                prov_dict["dead"] += cnt if st != "dead" else 0
                prov_dict["banned"] += cnt if st != "banned" else 0
        return out

    async def total_credits(self, provider: str) -> int:
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT COALESCE(SUM(credits),0) s FROM accounts WHERE provider=? AND status IN ('ok', 'active', 'working')",
                (provider,),
            )
            r = await cur.fetchone()
        return int(r["s"]) if r else 0

    async def cost_summary(self, provider: str) -> dict:
        """成本口径聚合（配合 P1-3「成本口径」主卡）。

        - total_credits_used：全部账号累计消耗积分（v6.5.1 起扣减累计）
        - total_images_used：累计出图次数
        - total_credits_earned：累计获得积分（签到）
        - avg_cost_per_image：平均每张成本 = 累计消耗 / 出图次数（无出图时 None）
        - accounts_with_usage / total_accounts：有消耗账号数与总数（口径覆盖率）
        """
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT COALESCE(SUM(credits_used_total),0) c_used,"
                " COALESCE(SUM(images_used),0) imgs,"
                " COALESCE(SUM(credits_earned_total),0) c_earned,"
                " COUNT(CASE WHEN COALESCE(images_used,0) > 0 THEN 1 END) used_accs,"
                " COUNT(*) total_accs"
                " FROM accounts WHERE provider=?",
                (provider,),
            )
            row = await cur.fetchone()
        c_used = int(row["c_used"] or 0)
        imgs = int(row["imgs"] or 0)
        return {
            "total_credits_used": c_used,
            "total_images_used": imgs,
            "total_credits_earned": int(row["c_earned"] or 0),
            "accounts_with_usage": int(row["used_accs"] or 0),
            "total_accounts": int(row["total_accs"] or 0),
            "avg_cost_per_image": round(c_used / imgs, 1) if imgs > 0 else None,
        }

    # ── 补号速率画像 (P3-4) ──────────────────────────────
    async def growth_stats(self, provider: str) -> dict:
        """号池补满速率画像：「每天新增账号数」+「距目标还需几天」。

        - new_in_24h: 最近 24h 新注册账号数（≈ 每日新增速率缓存）
        - new_in_7d / avg_daily_7d: 7 天新增 / 日均（平滑短窗抖动）
        - gap: 距目标还差的可用(ok/active)账号数
        - eta_days: 预计达标天数 = gap / 每日速率；速率为 0 时 None（无法估算）
        """
        now = time.time()
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute("SELECT COUNT(*) FROM accounts WHERE provider=?", (provider,))
            total = (await cur.fetchone())[0]
            cur = await conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE provider=? AND created_at >= ?",
                (provider, now - 86400),
            )
            new_in_24h = (await cur.fetchone())[0]
            cur = await conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE provider=? AND created_at >= ?",
                (provider, now - 7 * 86400),
            )
            new_in_7d = (await cur.fetchone())[0]
        ok = len(await self.get(provider))
        target = _pkg_attr("TARGET_NANOBANANA", TARGET_NANOBANANA)
        daily_rate = float(new_in_24h)
        gap = max(0, target - ok)
        eta_days = round(gap / daily_rate, 1) if daily_rate > 0 else None
        return {
            "total": int(total),
            "new_in_24h": int(new_in_24h),
            "new_in_7d": int(new_in_7d),
            "avg_daily_7d": round(new_in_7d / 7.0, 1),
            "ok": ok,
            "target": int(target),
            "gap": int(gap),
            "eta_days": eta_days,
        }

    async def dashboard(self) -> dict:
        """前端「号池」看板数据：包含 nanobanana 等所有受支持提供商。"""
        counts = await self.counts()
        out = {}
        all_providers = set(counts.keys()) | {"nanobanana"}
        for prov in all_providers:
            c = counts.get(prov, {})
            # 兼容读取各状态计数
            ok_cnt = c.get("ok", 0) or c.get("active", 0)
            working_cnt = c.get("working", 0)
            exhausted_cnt = c.get("exhausted", 0) or c.get("cooling", 0)
            dead_cnt = c.get("dead", 0) or c.get("banned", 0)
            registering_cnt = c.get("registering", 0)
            unregistered_cnt = c.get("unregistered", 0)

            target = _pkg_attr("TARGET_NANOBANANA", TARGET_NANOBANANA)
            # 总数按原始各状态去重汇总
            raw_total = sum(v for k, v in c.items() if k not in ("active", "cooling", "dead"))
            if raw_total == 0:
                raw_total = ok_cnt + working_cnt + exhausted_cnt + dead_cnt + registering_cnt + unregistered_cnt

            out[prov] = {
                "total": raw_total,
                "ok": ok_cnt,
                "active": ok_cnt,
                "working": working_cnt,
                "exhausted": exhausted_cnt,
                "cooling": exhausted_cnt,
                "dead": dead_cnt,
                "banned": dead_cnt,
                "registering": registering_cnt,
                "unregistered": unregistered_cnt,
                "credits": await self.total_credits(prov),
                "target": target,
                "auto_register": self.registerers.get(prov) is not None,
            }
        return out
