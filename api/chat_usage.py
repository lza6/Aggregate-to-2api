"""聊天 API 用量记录与额度统计。"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from . import config
from .proxy_pool import proxy_pool

_PERIOD_SECONDS = {
    "1h": 3600,
    "24h": 24 * 3600,
    "7d": 7 * 24 * 3600,
    "30d": 30 * 24 * 3600,
}


class ChatUsageTracker:
    """将聊天调用写入共享 DB，并提供聚合统计。"""

    def __init__(self, db: Any | None = None) -> None:
        self._db = db

    async def _get_db(self) -> Any:
        if self._db is not None:
            return self._db
        from .meta import db

        return db

    async def record(
        self,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        reasoning_tokens: int = 0,
        cost_usd: float | None = 0.0,
        tool_calls_count: int = 0,
        duration_ms: float = 0.0,
        success: bool = True,
        proxy_used: str | None = None,
        error: str | None = None,
    ) -> None:
        """记录一次调用；cost_usd 为成本（USD），免费渠道为 0，付费渠道由 provider 填充。"""
        db = await self._get_db()
        now_ts = time.time()
        now_dt = datetime.fromtimestamp(now_ts)
        day = now_dt.strftime("%Y-%m-%d")
        month = now_dt.strftime("%Y-%m")
        await db._enqueue_write(
            "INSERT INTO chat_usage "
            "(provider, model, prompt_tokens, completion_tokens, reasoning_tokens, "
            "tool_calls, duration_ms, success, proxy_used, error, cost_usd, day, month, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(provider),
                str(model),
                max(0, int(prompt_tokens or 0)),
                max(0, int(completion_tokens or 0)),
                max(0, int(reasoning_tokens or 0)),
                max(0, int(tool_calls_count or 0)),
                max(0.0, float(duration_ms or 0.0)),
                int(bool(success)),
                proxy_used,
                error,
                max(0.0, float(cost_usd or 0.0)),
                day,
                month,
                now_ts,
            ),
        )

    async def _query_one(self, sql: str, params: tuple[Any, ...]) -> Any:
        db = await self._get_db()
        await db._ensure_flushed()
        conn = await db._get_read_conn()
        cursor = await conn.execute(sql, params)
        return await cursor.fetchone()

    async def stats(self, period: str = "24h") -> dict[str, Any]:
        """返回时间窗总量、按模型分组以及本地日统计。"""
        seconds = _PERIOD_SECONDS.get(period)
        if seconds is None:
            raise ValueError(f"不支持的统计周期：{period}")
        now = time.time()
        cutoff = now - seconds
        where = "created_at >= ?"
        total_row = await self._query_one(
            "SELECT COUNT(*), COALESCE(SUM(prompt_tokens), 0), "
            "COALESCE(SUM(completion_tokens), 0), COALESCE(SUM(reasoning_tokens), 0), "
            "COALESCE(SUM(tool_calls), 0), AVG(duration_ms), "
            "COALESCE(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END), 0) "
            "FROM chat_usage WHERE " + where,
            (cutoff,),
        )
        total_calls = int(total_row[0] or 0)
        prompt_tokens = int(total_row[1] or 0)
        completion_tokens = int(total_row[2] or 0)
        reasoning_tokens = int(total_row[3] or 0)
        tool_calls = int(total_row[4] or 0)
        avg_duration = total_row[5]
        ok_calls = int(total_row[6] or 0)

        db = await self._get_db()
        await db._ensure_flushed()
        conn = await db._get_read_conn()
        model_cursor = await conn.execute(
            "SELECT model, provider, COUNT(*), COALESCE(SUM(prompt_tokens), 0), "
            "COALESCE(SUM(completion_tokens), 0) FROM chat_usage WHERE "
            + where
            + " GROUP BY model, provider ORDER BY COUNT(*) DESC, model",
            (cutoff,),
        )
        model_rows = await model_cursor.fetchall()

        provider_cursor = await conn.execute(
            "SELECT provider, COUNT(*), COALESCE(SUM(cost_usd), 0), "
            "COALESCE(SUM(prompt_tokens + completion_tokens + reasoning_tokens), 0) "
            "FROM chat_usage WHERE " + where + " GROUP BY provider ORDER BY COUNT(*) DESC, provider",
            (cutoff,),
        )
        provider_rows = await provider_cursor.fetchall()

        today_start = datetime.combine(datetime.now().date(), datetime.min.time()).timestamp()
        today_row = await self._query_one(
            "SELECT COUNT(*), COALESCE(SUM(prompt_tokens + completion_tokens + reasoning_tokens), 0) "
            "FROM chat_usage WHERE created_at >= ?",
            (today_start,),
        )
        # v6.6.0: 成本聚合（cost_usd 列）
        cost_row = await self._query_one(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM chat_usage WHERE " + where,
            (cutoff,),
        )
        cost_sql = await self._query_one(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM chat_usage WHERE created_at >= ?",
            (today_start,),
        )
        by_model = [
            {
                "model": row[0],
                "provider": row[1],
                "calls": int(row[2] or 0),
                "prompt_tokens": int(row[3] or 0),
                "completion_tokens": int(row[4] or 0),
            }
            for row in model_rows
        ]
        by_provider = [
            {
                "provider": row[0],
                "calls": int(row[1] or 0),
                "cost_usd": round(float(row[2] or 0), 6),
                "tokens": int(row[3] or 0),
            }
            for row in provider_rows
        ]
        return {
            "period": period,
            "total_calls": total_calls,
            "ok_calls": ok_calls,
            "fail_calls": max(0, total_calls - ok_calls),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "reasoning_tokens": reasoning_tokens,
            "tool_calls": tool_calls,
            "avg_duration_ms": round(float(avg_duration), 1) if avg_duration is not None else None,
            "today_calls": int(today_row[0] or 0),
            "today_tokens": int(today_row[1] or 0),
            "cost_usd": round(float(cost_row[0] or 0), 6),
            "today_cost_usd": round(float(cost_sql[0] or 0), 6),
            "by_model": by_model,
            "by_provider": by_provider,
        }

    async def cost_monthly(self, months: int = 12) -> list[dict[str, Any]]:
        """按月聚合 cost_usd + calls（M6-F3 成本可视化）。返回升序月份列表，当前月在末位。"""
        months = max(1, int(months))
        # 计算 months 个月前（含当前月）的起始月份标签（YYYY-MM）
        month_idx = datetime.now().year * 12 + (datetime.now().month - 1)
        start_idx = month_idx - (months - 1)
        start_year, start_month = divmod(start_idx, 12)
        start_month += 1
        start_label = f"{start_year:04d}-{start_month:02d}"
        db = await self._get_db()
        await db._ensure_flushed()
        conn = await db._get_read_conn()
        cursor = await conn.execute(
            "SELECT month, COALESCE(SUM(cost_usd), 0), COUNT(*) FROM chat_usage "
            "WHERE month IS NOT NULL AND month >= ? GROUP BY month ORDER BY month ASC",
            (start_label,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "month": row[0],
                "cost_usd": round(float(row[1] or 0), 6),
                "calls": int(row[2] or 0),
            }
            for row in rows
        ]

    async def cost_by_provider_model(self, months: int = 12) -> list[dict[str, Any]]:
        """按 provider+model 聚合 cost_usd + calls（M6-F3）。"""
        months = max(1, int(months))
        month_idx = datetime.now().year * 12 + (datetime.now().month - 1)
        start_idx = month_idx - (months - 1)
        start_year, start_month = divmod(start_idx, 12)
        start_month += 1
        start_label = f"{start_year:04d}-{start_month:02d}"
        db = await self._get_db()
        await db._ensure_flushed()
        conn = await db._get_read_conn()
        cursor = await conn.execute(
            "SELECT provider, model, COALESCE(SUM(cost_usd), 0), COUNT(*) FROM chat_usage "
            "WHERE month IS NOT NULL AND month >= ? GROUP BY provider, model ORDER BY provider, model",
            (start_label,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "provider": row[0],
                "model": row[1],
                "cost_usd": round(float(row[2] or 0), 6),
                "calls": int(row[3] or 0),
            }
            for row in rows
        ]

    async def cost_usd_for_range(self, start_ts: float, end_ts: float) -> float:
        """统计 [start_ts, end_ts) 时间窗内的 cost_usd 总和（/v1/cost 用）。"""
        db = await self._get_db()
        await db._ensure_flushed()
        conn = await db._get_read_conn()
        cursor = await conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM chat_usage WHERE created_at >= ? AND created_at < ?",
            (float(start_ts), float(end_ts)),
        )
        row = await cursor.fetchone()
        return round(float(row[0] or 0), 6)

    async def cost_by_provider(self, months: int = 12) -> list[dict[str, Any]]:
        """按 provider 聚合 cost_usd + calls + tokens（M6-F3 /v1/cost 的 by_provider）。"""
        months = max(1, int(months))
        month_idx = datetime.now().year * 12 + (datetime.now().month - 1)
        start_idx = month_idx - (months - 1)
        start_year, start_month = divmod(start_idx, 12)
        start_month += 1
        start_label = f"{start_year:04d}-{start_month:02d}"
        db = await self._get_db()
        await db._ensure_flushed()
        conn = await db._get_read_conn()
        cursor = await conn.execute(
            "SELECT provider, COUNT(*), COALESCE(SUM(cost_usd), 0), "
            "COALESCE(SUM(prompt_tokens + completion_tokens + reasoning_tokens), 0) "
            "FROM chat_usage WHERE month IS NOT NULL AND month >= ? "
            "GROUP BY provider ORDER BY provider",
            (start_label,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "provider": row[0],
                "calls": int(row[1] or 0),
                "cost_usd": round(float(row[2] or 0), 6),
                "tokens": int(row[3] or 0),
            }
            for row in rows
        ]

    async def remaining_credits(self) -> dict[str, Any]:
        """按可用代理数和每出口小时配额估算剩余额度。"""
        now = time.time()
        available = sum(1 for entry in proxy_pool.entries if entry.available(now))
        effective_proxies = max(available, 1)
        per_proxy = max(0, int(config.IF_TRYINGOPEN_HOURLY_PER_IP))
        used_row = await self._query_one(
            "SELECT COUNT(*) FROM chat_usage " "WHERE created_at > ? AND success = 1",
            (now - 3600,),
        )
        used = int(used_row[0] or 0)
        hourly_limit = effective_proxies * per_proxy
        return {
            "available_proxies": effective_proxies,
            "calls_per_proxy_per_hour": per_proxy,
            "hourly_limit": hourly_limit,
            "used_last_hour": used,
            "remaining": max(0, hourly_limit - used),
            "note": "按可用出口数量估算；代理池为空时按本机直连 1 个出口计算",
        }


chat_usage_tracker = ChatUsageTracker()

__all__ = ["ChatUsageTracker", "chat_usage_tracker"]
