"""AccountPool FSM 借还 mixin：借号/归还/封号/冷却/自愈/租约/预测（P0-F2 拆分）。

从 pool.py 拆出的状态机核心操作：borrow_account/release_account/mark_dead/
mark_cooling/wake_cooling_accounts/lease/predict_exhaustion/_reclaim_lease_timeout。
方法签名/SQL/状态字面量全部不变，仅物理位置迁移到本 mixin。

被 monkeypatch 的常量（SELFHEAL_MAX_RETRY）经 `_pkg_attr()` 运行时读包命名空间，
保持 `monkeypatch.setattr("api.account_pool.SELFHEAL_MAX_RETRY", ...)` 命中。
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from ._constants import (
    BORROW_LEASE_TIMEOUT_SECONDS,
    DEFAULT_COOLING_PERIOD_SECONDS,
    SELFHEAL_BACKOFF_BASE,
    SELFHEAL_BACKOFF_CAP,
    SELFHEAL_MAX_RETRY,
    _pkg_attr,
    log,
)
from .fsm import AccountStatus


class BorrowMixin:
    """FSM 借还/自愈 mixin，由 AccountPool 多继承组合。"""

    # ── 状态机核心操作 (FSM, 全 async) ──────────────────────────

    async def _reclaim_lease_timeout(self, provider: str) -> int:
        """回收超租约的 working 账号：超过 BORROW_LEASE_TIMEOUT_SECONDS 自动重置为 active，防止账号永久卡死。"""
        now = time.time()
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(
                "UPDATE accounts SET status='active', borrowed_at=NULL, updated_at=? "
                "WHERE provider=? AND status='working' AND borrowed_at IS NOT NULL AND (?-borrowed_at) > ?",
                (now, provider, now, BORROW_LEASE_TIMEOUT_SECONDS),
            )
            await conn.commit()
            reclaimed = cur.rowcount
        if reclaimed:
            log.info("自动回收超租约 working 账号: %d 个 (%s)", reclaimed, provider)
        return reclaimed

    async def borrow_account(self, provider: str, prefer_email: str | None = None) -> dict | None:
        """从 active (ok) 账号池原子借出一个账号并标记为 working 状态。"""
        now = time.time()
        conn = await self._ensure_conn()
        async with self._lock:
            # 先回收超时残留的 working 账号
            await conn.execute(
                "UPDATE accounts SET status='active', borrowed_at=NULL, updated_at=? "
                "WHERE provider=? AND status='working' AND borrowed_at IS NOT NULL AND (?-borrowed_at) > ?",
                (now, provider, now, BORROW_LEASE_TIMEOUT_SECONDS),
            )

            row = None
            if prefer_email:
                cur = await conn.execute(
                    "SELECT * FROM accounts WHERE provider=? AND email=? AND status IN ('active', 'ok') AND credits > 0",
                    (provider, prefer_email),
                )
                row = await cur.fetchone()

            if not row:
                # 按积分降序及最后更新升序挑选一个
                cur = await conn.execute(
                    "SELECT * FROM accounts WHERE provider=? AND status IN ('active', 'ok') AND credits > 0 "
                    "ORDER BY credits DESC, updated_at ASC LIMIT 1",
                    (provider,),
                )
                row = await cur.fetchone()

            if not row:
                # 如果没有 credits > 0 的，尝试任意 active (ok) 账号（如不需要 credits 的场景）
                cur = await conn.execute(
                    "SELECT * FROM accounts WHERE provider=? AND status IN ('active', 'ok') "
                    "ORDER BY updated_at ASC LIMIT 1",
                    (provider,),
                )
                row = await cur.fetchone()

            if not row:
                return None

            email = row["email"]
            await conn.execute(
                "UPDATE accounts SET status='working', borrowed_at=?, updated_at=? WHERE provider=? AND email=?",
                (now, now, provider, email),
            )
            await conn.commit()

            acc_dict = dict(row)
            acc_dict["status"] = "working"
            acc_dict["borrowed_at"] = now
            return acc_dict

    async def release_account(
        self, provider: str, email: str, new_credits: int | None = None, status: str | None = None, note: str = ""
    ) -> None:
        """请求完毕归还账号：更新积分并根据规则或指定状态转移。"""
        now = time.time()
        conn = await self._ensure_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT credits, status FROM accounts WHERE provider=? AND email=?", (provider, email)
            )
            cur_row = await cur.fetchone()
            if not cur_row:
                return

            credits_val = new_credits if new_credits is not None else cur_row["credits"]

            # 如果未显式指定目标状态，根据余额和当前状态自动推导
            target_status = status
            cooling_since = None
            if target_status is None:
                if credits_val is not None and credits_val <= 0:
                    target_status = "cooling"
                    cooling_since = now
                else:
                    target_status = "active"

            canonical_status = AccountStatus.canonical(target_status)
            if canonical_status in ("cooling", "exhausted") and cooling_since is None:
                cooling_since = now

            await conn.execute(
                "UPDATE accounts SET credits=?, status=?, note=CASE WHEN ? != '' THEN ? ELSE note END, "
                "cooling_since=COALESCE(?, cooling_since), borrowed_at=NULL, updated_at=? "
                "WHERE provider=? AND email=?",
                (credits_val, target_status, note, note, cooling_since, now, provider, email),
            )
            await conn.commit()

    async def mark_dead(self, provider: str, email: str, reason: str = "401/403 banned") -> None:
        """捕获封号/鉴权失效错误，将账号转移至 dead 状态。"""
        now = time.time()
        conn = await self._ensure_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE accounts SET status='dead', note=?, borrowed_at=NULL, updated_at=? WHERE provider=? AND email=?",
                (reason, now, provider, email),
            )
            await conn.commit()
        log.warning("账号标记封禁 [dead] %s (%s): %s", email, provider, reason)

    async def mark_cooling(self, provider: str, email: str, reason: str = "credits exhausted") -> None:
        """积分耗尽，将账号转移至 cooling 状态并记录冷却开始时间。

        P1-7: 进入新一轮 cooling 时清零自愈 retry 计数（重新从头计）。
        """
        now = time.time()
        conn = await self._ensure_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE accounts SET status='cooling', note=?, cooling_since=?, borrowed_at=NULL, updated_at=? "
                "WHERE provider=? AND email=?",
                (reason, now, now, provider, email),
            )
            await conn.commit()
        self._selfheal_retry.pop((provider, email), None)
        log.info("账号进入冷却 [cooling] %s (%s): %s", email, provider, reason)

    # ── P1-7 余额预测 ──────────────────────────────────────
    async def predict_exhaustion(self, provider: str) -> dict:
        """基于近 7 天消耗速率 + 当前余额，预测号池耗尽时间。

        口径（近似）：credits_used_total 为账号累计消耗（无逐次历史明细），
        以近 7 天内有使用记录的账号累计消耗 / 实际使用跨度天数 估算速率——
        跨度取 [min(last_used_at), max(last_used_at)]，下限 1 小时防除零。
        返回:
          - hours_to_exhaustion: float | None（无消耗数据/零速率/空池时 None）
          - burn_rate_per_day: float（日均积分消耗速率）
          - current_credits: int（当前可用余额：ok/active/working）
        """
        conn = await self._ensure_conn()
        now = time.time()
        seven_days_ago = now - 7 * 86400
        async with self._lock:
            cur = await conn.execute(
                "SELECT COALESCE(SUM(credits),0) s FROM accounts "
                "WHERE provider=? AND status IN ('ok', 'active', 'working')",
                (provider,),
            )
            r = await cur.fetchone()
            current_credits = int(r["s"]) if r else 0

            cur = await conn.execute(
                "SELECT COALESCE(SUM(credits_used_total),0) used, "
                " MIN(last_used_at) lo, MAX(last_used_at) hi, "
                " COUNT(CASE WHEN last_used_at IS NOT NULL THEN 1 END) used_accs "
                " FROM accounts WHERE provider=? AND last_used_at >= ?",
                (provider, seven_days_ago),
            )
            row = await cur.fetchone()
        used = int(row["used"] or 0)
        used_accs = int(row["used_accs"] or 0)
        lo = row["lo"]
        hi = row["hi"]
        if used_accs == 0 or used == 0 or lo is None or hi is None:
            return {"hours_to_exhaustion": None, "burn_rate_per_day": 0.0, "current_credits": current_credits}
        span_seconds = max(float(hi - lo), 3600.0)  # 下限 1 小时防除零
        span_days = span_seconds / 86400.0
        burn_per_day = used / span_days
        if burn_per_day <= 0 or current_credits <= 0:
            return {"hours_to_exhaustion": None, "burn_rate_per_day": 0.0, "current_credits": current_credits}
        hours = current_credits / burn_per_day * 24.0
        return {
            "hours_to_exhaustion": round(hours, 1),
            "burn_rate_per_day": round(burn_per_day, 2),
            "current_credits": current_credits,
        }

    async def wake_cooling_accounts(
        self, provider: str | None = None, cooling_timeout: float = DEFAULT_COOLING_PERIOD_SECONDS
    ) -> int:
        """扫描 cooling / exhausted 账号，超过冷却时间或每日重置时唤醒恢复为 active。

        P1-7 FSM 自愈：当 provider 已注入 registerer 时走自愈路径——
        对每个到期 cooling 账号尝试签到恢复（不直接无条件转 active）：
          - 签到成功（返回有效余额）→ 转 active 并清零 retry 计数
          - 签到失败 → retry+1，重置 cooling_since 实现指数退避（下次唤醒需再等
            cooling_timeout * backoff_base^retry，封顶 7d）；retry 超过
            IF_ACCOUNT_SELFHEAL_MAX_RETRY 才转 dead
        无 registerer 时保持原「到期直接唤醒」行为（向后兼容）。
        """
        now = time.time()
        conn = await self._ensure_conn()
        async with self._lock:
            conds = ["status IN ('cooling', 'exhausted')"]
            args: list[object] = []
            if provider:
                conds.append("provider=?")
                args.append(provider)
            # 条件：cooling_since 超时 或 cooling_since 为 NULL
            conds.append("(cooling_since IS NULL OR (? - cooling_since) >= ?)")
            args.extend([now, cooling_timeout])

            where_clause = " WHERE " + " AND ".join(conds)
            cur = await conn.execute(f"SELECT provider, email, credits FROM accounts {where_clause}", args)
            rows = await cur.fetchall()
            if not rows:
                return 0

            # 无 registerer 的 provider → 原到期直接唤醒（向后兼容）
            legacy_rows: list = []
            healed: int = 0
            for r in rows:
                prov = r["provider"]
                email = r["email"]
                reg = self.registerers.get(prov)
                if reg is None or not hasattr(reg, "checkin"):
                    legacy_rows.append(r)
                    continue
                # 自愈路径：尝试签到恢复
                try:
                    ok = await reg.checkin(dict(r))
                except Exception as e:
                    log.warning("自愈签到异常 %s/%s: %s", prov, email, e)
                    ok = None
                key = (prov, email)
                if ok:
                    # 签到成功 → 转 active，清零 retry
                    if isinstance(ok, dict):
                        credits = int(ok.get("credits") or 0)
                    else:
                        credits = int(ok or 0)
                    await conn.execute(
                        "UPDATE accounts SET status='active', credits=?, cooling_since=NULL, updated_at=? "
                        "WHERE provider=? AND email=?",
                        (credits, now, prov, email),
                    )
                    self._selfheal_retry.pop(key, None)
                    healed += 1
                    log.info("FSM 自愈成功 %s/%s → active (credits=%d)", prov, email, credits)
                else:
                    # 签到失败 → retry+1 + 指数退避（重置 cooling_since）
                    retry = self._selfheal_retry.get(key, 0) + 1
                    self._selfheal_retry[key] = retry
                    max_retry = _pkg_attr("SELFHEAL_MAX_RETRY", SELFHEAL_MAX_RETRY)
                    if retry >= max_retry:
                        await conn.execute(
                            "UPDATE accounts SET status='dead', note=?, cooling_since=NULL, updated_at=? "
                            "WHERE provider=? AND email=?",
                            (f"自愈连续 {retry} 次失败转 dead", now, prov, email),
                        )
                        self._selfheal_retry.pop(key, None)
                        log.warning("FSM 自愈耗尽 %s/%s → dead (retry=%d)", prov, email, retry)
                    else:
                        # 指数退避：下次唤醒冷却 = cooling_timeout * base^retry，封顶
                        backoff = min(
                            cooling_timeout * (SELFHEAL_BACKOFF_BASE**retry),
                            SELFHEAL_BACKOFF_CAP,
                        )
                        await conn.execute(
                            "UPDATE accounts SET cooling_since=?, note=?, updated_at=? WHERE provider=? AND email=?",
                            (now - cooling_timeout + backoff, f"selfheal retry={retry}", now, prov, email),
                        )
                        log.info("FSM 自愈退避 %s/%s (retry=%d, 下次唤醒 +%.0fs)", prov, email, retry, backoff)

            # 无 registerer 的账号：到期直接唤醒（原逻辑）
            for r in legacy_rows:
                await conn.execute(
                    "UPDATE accounts SET status='active', cooling_since=NULL, updated_at=? WHERE provider=? AND email=?",
                    (now, r["provider"], r["email"]),
                )
                healed += 1
            await conn.commit()
            if healed:
                log.info("自动唤醒冷却账号: %d 个 (%s)", healed, provider or "all")
            return healed

    @asynccontextmanager
    async def lease(self, provider: str, prefer_email: str | None = None) -> AsyncGenerator[dict | None, None]:
        """异步上下文管理器：借号并在退出时自动归还/异常处理。

        P2-3 后 borrow/release/mark_dead 均已 async，lease 直接 await 调用。
        """
        acc = await self.borrow_account(provider, prefer_email)
        if not acc:
            yield None
            return
        email = acc["email"]
        try:
            yield acc
        except Exception as e:
            # 如果是 401/403/banned 则 mark_dead，否则正常归还
            err_str = str(e).lower()
            try:
                if any(
                    k in err_str for k in ("401", "403", "unauthorized", "forbidden", "banned", "account suspended")
                ):
                    await self.mark_dead(provider, email, reason=str(e)[:100])
                else:
                    await self.release_account(provider, email)
            except Exception as release_err:
                log.warning("账号归还失败 (%s/%s), 原始异常: %s", provider, email, release_err)
            raise
        else:
            await self.release_account(provider, email)
