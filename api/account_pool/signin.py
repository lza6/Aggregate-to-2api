"""AccountPool 签到 mixin：签到画像落库 + 每日签到巡检循环（P0-F2 拆分）。

从 pool.py 拆出：set_checkin/set_checkin_profile/_load_checkin_batch/
_daily_checkin_loop。方法签名/SQL/列名全部不变，仅物理位置迁移到本 mixin。
"""

from __future__ import annotations

import asyncio
import time

from ._constants import log


class SigninMixin:
    """签到画像 + 每日签到巡检 mixin，由 AccountPool 多继承组合。"""

    async def set_checkin(self, provider: str, email: str, checkin_at: float) -> None:
        conn = await self._ensure_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE accounts SET checkin_at=? WHERE provider=? AND email=?", (checkin_at, provider, email)
            )
            await conn.commit()

    async def set_checkin_profile(
        self,
        provider: str,
        email: str,
        checkin_at: float,
        cycle_day: int = 0,
        reward: int = 0,
        next_claim_at: float | None = None,
    ) -> None:
        """v6.3.4: 签到成功后一次性落库完整画像。

        - checkin_at：本次签到时间戳
        - checkin_cycle_day：上游 claim 响应的 cycleDay（7 天周期内第几天）
        - checkin_total：累计签到天数（自增 1）
        - credits_earned_total：累计获得积分（累计 reward）
        - next_claim_at：上游 nextClaimAt（美区时区重置点）
        """
        conn = await self._ensure_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE accounts SET checkin_at=?, checkin_cycle_day=?,"
                " checkin_total=COALESCE(checkin_total,0)+1,"
                " credits_earned_total=COALESCE(credits_earned_total,0)+?,"
                " next_claim_at=?, updated_at=?"
                " WHERE provider=? AND email=?",
                (checkin_at, int(cycle_day or 0), int(reward or 0), next_claim_at, time.time(), provider, email),
            )
            await conn.commit()

    async def _load_checkin_batch(self, provider: str, cutoff: float, size: int) -> list[dict]:
        """SQL 层过滤签到账号（async + 锁保护），供 _daily_checkin_loop 调用。

        P2-3: 已 async，直接在事件循环线程跑（aiosqlite 内部线程池处理 I/O，不阻塞 loop）。
        """
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT * FROM accounts WHERE provider=? AND status IN ('ok', 'active') "
                "AND (checkin_at IS NULL OR checkin_at < ?) ORDER BY checkin_at ASC LIMIT ?",
                (provider, cutoff, size),
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def _daily_checkin_loop(self, provider: str) -> None:
        """nanobanana：定时检查签到（按时区与间隔），按批次处理避免 O(n)。"""
        BATCH_SIZE = 500  # 每轮最多处理 500 个账号，避免单次全表扫描阻塞事件循环
        first_cycle = True
        while True:
            try:
                # 启动后先等 60s，让 provider/代理池完成初始化；随后每 30 分钟巡检。
                await asyncio.sleep(60 if first_cycle else 1800)
                first_cycle = False
                reg = self.registerers.get(provider)
                if reg is None:
                    continue
                now = time.time()
                cutoff = now - 20 * 3600  # 距上次签到 >20h → 补签
                # P2-3: _load_checkin_batch 已 async，直接 await（不再 to_thread）
                rows = await self._load_checkin_batch(provider, cutoff, BATCH_SIZE)
                if not rows:
                    continue
                for row in rows:
                    acc = dict(row)
                    try:
                        ok = await reg.checkin(acc)
                        if ok:
                            # v6.3.4: checkin 现返回 {credits, reward?, cycle_day?, next_claim_at?} 画像 dict
                            # 兼容旧的 int 返回（仅余额）
                            if isinstance(ok, dict):
                                credits = int(ok.get("credits") or 0)
                                await self.set_checkin_profile(
                                    provider,
                                    acc["email"],
                                    time.time(),
                                    cycle_day=int(ok.get("cycle_day") or 0),
                                    reward=int(ok.get("reward") or 0),
                                    next_claim_at=ok.get("next_claim_at"),
                                )
                            else:
                                credits = int(ok or 0)
                                await self.set_checkin(provider, acc["email"], time.time())
                            if credits:
                                await self.update_credits(provider, acc["email"], credits)
                            await self.mark(provider, acc["email"], "active")
                            continue
                        # checkin 返回 None（cookie 失效）→ 尝试用保存的密码重新登录续期
                        # 注意：checkin 失败不一定是 cookie 过期（也可能是网络/求解临时故障），
                        # 用连续失败计数（note 里的 fail:N 标记）代替一次就标 dead。
                        if acc.get("password") and hasattr(reg, "re_login"):
                            re = await reg.re_login(acc["email"], acc["password"])
                            if re and re.get("cookie"):
                                await self.add(
                                    provider,
                                    acc["email"],
                                    re["cookie"],
                                    password=acc.get("password"),
                                    credits=int(acc.get("credits") or 0),
                                    status="active",
                                    note=acc.get("note") or "",
                                    register_ip=acc.get("register_ip") or "",
                                )
                                log.info("nanobanana cookie 续期成功 %s", acc["email"])
                            else:
                                # 累计失败计数，>=3 次才标 dead
                                prev_note = acc.get("note") or ""
                                fail_n = int(prev_note.split("fail:")[1]) if "fail:" in prev_note else 1
                                if fail_n >= 3:
                                    await self.mark(
                                        provider, acc["email"], "dead", note=f"cookie 续期连续 {fail_n} 次失败"
                                    )
                                else:
                                    await self.mark(provider, acc["email"], "active", note=f"fail:{fail_n + 1}")
                                    log.warning("nanobanana %s checkin+re_login 失败 (第 %d 次)", acc["email"], fail_n)
                        else:
                            await self.mark(provider, acc["email"], "dead", note="cookie 失效（无密码可续期）")
                    except Exception as e:
                        log.warning("nanobanana 签到失败 %s: %s", acc["email"], e)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("签到循环异常 %s: %s", provider, e)
