"""MAB-EWMA 自适应路由引擎：结合时延、成功率、负载的多臂赌博机路由。

痛点（v3.2+）：上游网络突发抖动 / Turnstile 求解器排队时，静态路由或单一成功率
路由容易把流量继续打入慢节点。本引擎用 Epsilon-Greedy-Decay 探索 + EWMA 指数加权
移动平均时延 + 熔断器，实时加权打分选出当次最优 provider。

算法：Score = (成功率 / log10(EWMA时延)) * 负载惩罚
 - 成功率：Laplace 平滑（避免样本少时震荡）
 - EWMA 时延：alpha=0.2 平滑，失败时惩罚放大 1.5x（快速感知抖动）
 - 负载惩罚：in_flight 越高分越低（先进先出，防把流量灌进忙节点）
 - 熔断：失败率 > 50% 且样本 >= 5 → OPEN 30s；到期 HALF_OPEN 试放一个请求
 - 探索：epsilon 概率随机选（探测可能恢复的 provider，随样本数衰减）

路由决策记录（环形缓冲，内存，最多 1000 条）供前端"路由记录"展示，
让开发者知道自己的请求被哪个 provider 处理、为什么。

P3-1 可观测/可恢复（v6.8.x）：
 - 新增可选 SQLite 持久化（IF_ROUTING_DB / routing_db_file 指向独立轻量 sqlite 文件，
   默认空 = 关闭，完全向后兼容）。持久化不侵入主 DB 的 schema 语义（requests/chat_usage），
   用独立 db 文件 + 独立连接。
 - record() 写入路由决策历史；record_result() 额外落 per-provider 时延/成败观测
   （routing_outcomes 表），供重启后 warm 冷启动 EWMA。
 - restore() 在初始化时加载最近 _MAX_RECORDS 条到内存环形缓冲；冷启动且 nodes 为空时，
   用持久化的 per-provider min/max 时延经验值初始化 EWMA 参数（warm），避免全零冷启动首路由乱选。
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import sqlite3
import threading
import time
from dataclasses import dataclass

log = logging.getLogger("adaptive_router")

_MAX_RECORDS = 1000
_OPEN_COOLDOWN = 30.0  # 熔断时长（秒）
_OPEN_FAIL_RATIO = 0.5  # 触发熔断的失败率阈值
_OPEN_MIN_SAMPLES = 5  # 触发熔断的最少样本数
_LATENCY_FLOOR = 100.0  # 时延下限（平滑 log，防除零/负值）
_INIT_EWMA = 2000.0  # 初始预估时延（2s，冷启动公平）
_ALPHA = 0.2  # EWMA 平滑系数
_OUTCOME_RETENTION_DAYS = 14  # routing_outcomes 观测保留天数（warm 数据源）
_OUTCOME_PRUNE_EVERY = 200  # 每 N 次观测触发一次陈旧数据清理


def _run_async(func, *args):
    """在运行中的事件循环里用线程池执行同步阻塞调用；无 running loop 则同步降级。

    P3-1 R1：record_direct/record_fallback/record_result 可能被 async 调用链
    （dispatch._dispatch_generate）或同步调用链（registry.provider_for 的同步分支）
    触发。async 上下文里把 sqlite3 同步写丢线程池防阻塞 loop；纯同步上下文（无 loop）
    直接执行即可（本就没有事件循环可阻塞）。
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        func(*args)
        return
    loop.run_in_executor(None, func, *args)


@dataclass
class ProviderNodeStats:
    """单个 provider 的路由统计。

    v8.0 P1-3：追加 Thompson Sampling（Beta 分布后验）+ UCB1（冷启动置信上界）参数。
    - alpha/beta：Beta 分布参数，成功 alpha+=1，失败 beta+=1；后验采样选 provider。
    - total_pulls：UCB1 全局计数（所有 provider 累计拉取次数），冷启动强探索。
    冷启动（样本 < 阈值）用 UCB1，样本充足切 Thompson（贝叶斯后验更精准）。

    v8.1 P1-A5（M10）：新增 cooldown_until（CooldownCache 熔断）+ retry_after_seconds
    （尊重上游 Retry-After 头，参考 litellm CooldownCache）。cooldown_until > now 时
    provider 被 select_best 视为不可用（与 circuit_state OPEN 互补）。
    """

    provider_id: str
    success_count: int = 0
    failure_count: int = 0
    ewma_latency_ms: float = _INIT_EWMA
    in_flight_requests: int = 0
    circuit_state: str = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
    circuit_open_until: float = 0.0
    consecutive_failures: int = 0
    last_result_ts: float = 0.0
    # v8.0 P1-3: Thompson Sampling（Beta 分布后验）
    alpha: float = 1.0
    beta: float = 1.0
    # v8.0 P1-3: UCB1 全局计数（本 provider 被选次数）
    pulls: int = 0
    # v8.1 P1-A5（M10）: CooldownCache 熔断 + Retry-After 尊重
    # cooldown_until：连续失败或上游 429 Retry-After 触发的冷却到期时间戳。
    # 0.0=未冷却；> now 时 select_best 跳过此 provider（与 circuit_state OPEN 互补）。
    cooldown_until: float = 0.0
    # retry_after_seconds：最近一次上游 Retry-After 头解析值（秒），供 node_snapshot 观测
    retry_after_seconds: float = 0.0


@dataclass
class RoutingRecord:
    """一次路由决策（供前端路由记录展示）。"""

    ts: float
    request_id: str
    model: str
    selected_provider: str
    requested_provider: str  # 原始（fallback 后真实处理的 provider 见 selected）
    score: float
    scores: dict[str, float]  # 所有候选的评分快照
    latency_ms: int = 0
    success: bool | None = None  # None=尚未完成（fallback 时请求还在途）
    reason: str = "best_score"


class RoutingRecordStore:
    """路由决策 / 观测历史的独立轻量 SQLite 归档（P3-1 可恢复）。

    设计取向（对齐 account_pool/email_pool 已验证的模式）：
    - 独立 sqlite 文件 + 独立连接（check_same_thread=False + WAL + busy_timeout），
      绝不侵入主 DB 的 requests/chat_usage 等业务表，schema 语义完全隔离。
    - 单连接 + threading.Lock 串行化所有读写：路由记录是「每请求一条」，单行 WAL
      插入为微秒级轻量写，不会显著阻塞事件循环（与 account_pool 同源反模式治理注释）。
    - 两表：
        routing_records  路由决策历史（ts/request/model/provider/score/scores/latency/success/reason）
        routing_outcomes per-provider 时延/成败观测（warm 冷启动 EWMA 的 min/max 数据源）

    显式 close() 关闭连接；进程回收由 sqlite3 自动完成。
    """

    def __init__(self, db_path: str) -> None:
        self._path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._lock = threading.Lock()
        self._outcome_writes = 0
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS routing_records (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts                REAL NOT NULL,
                    request_id        TEXT DEFAULT '',
                    model             TEXT DEFAULT '',
                    selected_provider TEXT NOT NULL,
                    requested_provider TEXT DEFAULT '',
                    score             REAL DEFAULT 0,
                    scores            TEXT DEFAULT '{}',
                    latency_ms        REAL DEFAULT 0,
                    success           INTEGER,
                    reason            TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_routing_records_ts ON routing_records(ts);
                CREATE TABLE IF NOT EXISTS routing_outcomes (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id TEXT NOT NULL,
                    ts          REAL NOT NULL,
                    latency_ms  REAL NOT NULL,
                    success     INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_routing_outcomes_provider ON routing_outcomes(provider_id, ts);
                """
            )
            self._conn.commit()

    # ── 写 ──
    def append(self, rec: RoutingRecord) -> None:
        """追加一条路由决策历史（同步轻量写；调用处已持 self._lock，此处仅取本锁）。"""
        with self._lock:
            self._conn.execute(
                "INSERT INTO routing_records"
                " (ts, request_id, model, selected_provider, requested_provider, score,"
                "  scores, latency_ms, success, reason)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rec.ts,
                    rec.request_id,
                    rec.model,
                    rec.selected_provider,
                    rec.requested_provider,
                    rec.score,
                    json.dumps(rec.scores if rec.scores else {}),
                    rec.latency_ms,
                    None if rec.success is None else int(bool(rec.success)),
                    rec.reason,
                ),
            )
            self._conn.commit()

    def record_outcome(self, provider_id: str, latency_ms: float, is_success: bool) -> None:
        """记录一次 per-provider 调用时延/成败观测（warm 数据源）。"""
        with self._lock:
            self._conn.execute(
                "INSERT INTO routing_outcomes (provider_id, ts, latency_ms, success)"
                " VALUES (?, ?, ?, ?)",
                (provider_id, time.time(), float(latency_ms), int(bool(is_success))),
            )
            self._outcome_writes += 1
            if self._outcome_writes >= _OUTCOME_PRUNE_EVERY:
                self._outcome_writes = 0
                cutoff = time.time() - _OUTCOME_RETENTION_DAYS * 86400
                self._conn.execute("DELETE FROM routing_outcomes WHERE ts < ?", (cutoff,))
            self._conn.commit()

    # ── 读 ──
    def history(self, limit: int = 50, from_ts: float | None = None) -> list[dict]:
        """持久化路由历史（时间升序，最新在尾）。可带 from_ts 过滤。"""
        with self._lock:
            if from_ts is not None:
                cur = self._conn.execute(
                    "SELECT * FROM ("
                    "  SELECT * FROM routing_records WHERE ts >= ? ORDER BY ts DESC LIMIT ?"
                    ") ORDER BY ts ASC",
                    (float(from_ts), limit),
                )
            else:
                cur = self._conn.execute(
                    "SELECT * FROM (SELECT * FROM routing_records ORDER BY ts DESC LIMIT ?)"
                    " ORDER BY ts ASC",
                    (limit,),
                )
            rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def warm_params(self) -> dict[str, dict]:
        """per-provider 时延经验值（min/max，来自真实调用观测），供冷启动 EWMA warm。"""
        with self._lock:
            cur = self._conn.execute(
                "SELECT provider_id, MIN(latency_ms), MAX(latency_ms)"
                " FROM routing_outcomes WHERE latency_ms > 0 GROUP BY provider_id"
            )
            rows = cur.fetchall()
        return {
            r[0]: {"min_latency": float(r[1] or 0), "max_latency": float(r[2] or 0)}
            for r in rows
        }

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        scores = row["scores"] or "{}"
        try:
            scores_dict = json.loads(scores)
        except (ValueError, TypeError):
            scores_dict = {}
        return {
            "ts": float(row["ts"]),
            "request_id": row["request_id"] or "",
            "model": row["model"] or "",
            "requested_provider": row["requested_provider"] or "",
            "selected_provider": row["selected_provider"],
            "score": round(float(row["score"] or 0), 4),
            "scores": {k: round(float(v), 4) for k, v in scores_dict.items()} if scores_dict else {},
            "latency_ms": row["latency_ms"],
            "success": None if row["success"] is None else bool(row["success"]),
            "reason": row["reason"] or "",
        }

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass


class AdaptiveRouter:
    """多提供商自适应路由引擎。

    线程安全策略：保留 threading.Lock（非 asyncio.Lock）。所有 record_*/select_best/
    node_snapshot 方法为同步、操作纯内存 dict（微秒级）。record_result 由 dispatch.py
    async _dispatch_generate 经同步调用链触发（registry.adaptive_router.record_result），
    换 asyncio.Lock 会把 record_result/select_best/node_snapshot 全部传染成 async，污染
    provider_for（同步）等调用链。asyncio 单线程事件循环无竞争零阻塞，此锁非阻塞源。
    真正的 async 阻塞源是 sqlite3 I/O（见 account_pool/email_pool 的同步 sqlite3 混入）。

    P3-1 可恢复：传 db_path 时启用 SQLite 持久化（独立轻量文件），__init__ 内自动
    restore() 加载最近历史并 warm EWMA；不传则完全保持旧的内存态行为（向后兼容）。
    """

    def __init__(
        self,
        alpha: float = _ALPHA,
        initial_explore_rate: float = 0.10,
        db_path: str = "",
    ) -> None:
        self.alpha = alpha
        self.base_explore_rate = initial_explore_rate
        self._lock = threading.Lock()
        self.nodes: dict[str, ProviderNodeStats] = {}
        self._records: list[RoutingRecord] = []
        self._store: RoutingRecordStore | None = None
        if db_path:
            try:
                self._store = RoutingRecordStore(db_path)
            except Exception:
                # 持久化失败不影响路由主路径（降级为纯内存）
                self._store = None
        self.restore()

    # ── 内部工具 ──
    @staticmethod
    def _record_to_dict(r: RoutingRecord) -> dict:
        return {
            "ts": r.ts,
            "request_id": r.request_id,
            "model": r.model,
            "requested_provider": r.requested_provider,
            "selected_provider": r.selected_provider,
            "score": round(r.score, 4),
            "scores": {k: round(v, 4) for k, v in r.scores.items()},
            "latency_ms": r.latency_ms,
            "success": r.success,
            "reason": r.reason,
        }

    def _record(self, rec: RoutingRecord) -> None:
        """环形缓冲写入（容量封顶，保留最新）+ 可选持久化。

        P3-1 R1 修复：持久化写（sqlite3 同步 I/O）经 asyncio.to_thread 丢入线程池，
        不阻塞事件循环（record_direct/record_fallback 是每个生图请求的必经链路）。
        内存 buf 写保持在事件循环内（微秒级），仅 sqlite 部分走线程池。
        注意 from api.providers.registry.provider_for 可能经同步路径触发本方法，
        该处无 running loop → 降级同步执行（持久化仍生效，只是可能阻塞，但该路径
        本身是同步调用链，无事件循环可阻塞）。
        """
        self._records.append(rec)
        if len(self._records) > _MAX_RECORDS:
            self._records = self._records[-_MAX_RECORDS:]
        if self._store is not None:
            try:
                _run_async(self._store.append, rec)
            except Exception:
                pass

    def records(self, limit: int = 50, from_ts: float | None = None) -> list[dict]:
        """返回最近 limit 条路由记录（时间戳倒序；from_ts 提供时按持久化历史过滤）。"""
        if from_ts is not None:
            if self._store is not None:
                return self._store.history(limit=limit, from_ts=from_ts)
            with self._lock:
                rows = [r for r in self._records if r.ts >= from_ts][-limit:]
            return [self._record_to_dict(r) for r in rows]
        with self._lock:
            rows = self._records[-limit:]
        return [self._record_to_dict(r) for r in rows]

    # ── 可恢复（P3-1）──
    def restore(self, limit: int = _MAX_RECORDS) -> int:
        """启动时从 SQLite 恢复最近 limit 条决策历史到内存，并 warm 冷启动 EWMA。

        返回恢复条数。无存储时为空操作（0）。
        """
        if self._store is None:
            return 0
        recs = self._store.history(limit=limit)
        restored = len(recs)
        with self._lock:
            self._records = [RoutingRecord(
                ts=r["ts"],
                request_id=r["request_id"],
                model=r["model"],
                selected_provider=r["selected_provider"],
                requested_provider=r["requested_provider"],
                score=r["score"],
                scores=r["scores"],
                latency_ms=r["latency_ms"],
                success=r["success"],
                reason=r["reason"],
            ) for r in recs]
            if not self.nodes:
                self._warm_from_store()
        return restored

    def _warm_from_store(self) -> None:
        """冷启动：nodes 为空时用持久化 per-provider min/max 时延经验值初始化 EWMA。

        取经验区间中点作为 EWMA 种子（不低于 _LATENCY_FLOOR），避免首路由全用
        _INIT_EWMA=2000ms 的同质初值导致分数拉平、乱选。
        """
        if self._store is None:
            return
        try:
            params = self._store.warm_params()
        except Exception:
            return
        for pid, p in params.items():
            lo = float(p.get("min_latency") or 0)
            hi = float(p.get("max_latency") or 0)
            if hi <= 0:
                continue
            warm = max(_LATENCY_FLOOR, (lo + hi) / 2.0)
            st = self.nodes.setdefault(pid, ProviderNodeStats(provider_id=pid))
            st.ewma_latency_ms = warm

    # ── 统计更新 ──
    def record_result(self, provider_id: str, latency_ms: float, is_success: bool) -> None:
        """记录一次调用结果（时延 + 成败），更新 EWMA、熔断状态与持久化观测。"""
        with self._lock:
            stats = self.nodes.setdefault(provider_id, ProviderNodeStats(provider_id=provider_id))
            stats.in_flight_requests = max(0, stats.in_flight_requests - 1)
            stats.last_result_ts = time.time()
            if is_success:
                stats.success_count += 1
                stats.consecutive_failures = 0
                stats.alpha += 1.0  # v8.0 P1-3: Beta 后验更新（成功）
                stats.ewma_latency_ms = self.alpha * max(0.0, latency_ms) + (1 - self.alpha) * stats.ewma_latency_ms
                if stats.circuit_state == "HALF_OPEN":
                    # HALF_OPEN 时成功一个 → 熔断确认恢复
                    stats.circuit_state = "CLOSED"
            else:
                stats.failure_count += 1
                stats.consecutive_failures += 1
                stats.beta += 1.0  # v8.0 P1-3: Beta 后验更新（失败）
                # 失败惩罚：EWMA 时延放大 1.5x（封顶 5s），快速感知抖动
                stats.ewma_latency_ms = max(_INIT_EWMA, stats.ewma_latency_ms * 1.5)
                # 熔断判定：失败率 > 阈值且样本足够
                total = stats.success_count + stats.failure_count
                if total >= _OPEN_MIN_SAMPLES and (stats.failure_count / total) > _OPEN_FAIL_RATIO:
                    stats.circuit_state = "OPEN"
                    stats.circuit_open_until = time.time() + _OPEN_COOLDOWN
        # 释放 self._lock 后再做持久化（避免嵌套锁；低频率轻量写，不影响路由主路径）
        if self._store is not None:
            try:
                # R1：record_outcome 内部 sqlite3 同步写 → 线程池防阻塞（无 loop 则同步降级）
                _run_async(self._store.record_outcome, provider_id, float(latency_ms), bool(is_success))
            except Exception:
                pass

    def record_inflight(self, provider_id: str, delta: int = 1) -> None:
        """在途请求计数（调用前 +1，结果回来时由 record_result -1）。"""
        with self._lock:
            stats = self.nodes.setdefault(provider_id, ProviderNodeStats(provider_id=provider_id))
            stats.in_flight_requests = max(0, stats.in_flight_requests + delta)

    def record_cooldown(self, provider_id: str, retry_after_seconds: float | None = None) -> None:
        """v8.1 P1-A5（M10）：CooldownCache 熔断——连续失败或上游 429 时冷却 provider。

        参考 litellm CooldownCache：
        - 连续失败触发冷却 _OPEN_COOLDOWN 秒（与 circuit_state OPEN 互补）
        - 上游 Retry-After 头非空时，尊重其值（取 max(retry_after, _OPEN_COOLDOWN)）
        - cooldown_until > now 期间，select_best 视此 provider 为不可用
        - 成功时 record_result 清零 consecutive_failures，但 cooldown 需等到期自动解

        注意：retry_after_seconds 显式传入短值（如测试 0.01s）时，以传入值为准
        （允许短冷却测试）；仅当未传 retry_after 时才用默认 _OPEN_COOLDOWN。
        """
        with self._lock:
            stats = self.nodes.setdefault(provider_id, ProviderNodeStats(provider_id=provider_id))
            now = time.time()
            if retry_after_seconds is not None and retry_after_seconds > 0:
                stats.retry_after_seconds = float(retry_after_seconds)
                # 显式传入时以传入值为准（允许短冷却测试）；不强制 max 下限
                cooldown_seconds = float(retry_after_seconds)
            else:
                cooldown_seconds = _OPEN_COOLDOWN
            stats.cooldown_until = now + cooldown_seconds
            log.info(
                "provider %s 进入 CooldownCache 冷却 %.0fs（retry_after=%s）",
                provider_id,
                cooldown_seconds,
                retry_after_seconds,
            )

    def is_in_cooldown(self, provider_id: str) -> bool:
        """v8.1 P1-A5（M10）：provider 是否在 CooldownCache 冷却期。"""
        with self._lock:
            stats = self.nodes.get(provider_id)
            if stats is None:
                return False
            return stats.cooldown_until > time.time()

    def record_retry_after(self, provider_id: str, retry_after_header: str | None) -> None:
        """v8.1 P1-A5（M10）：解析上游 Retry-After 头并触发冷却。

        供 dispatch / provider 调用链在收到 429 + Retry-After 时上报，
        让路由引擎尊重上游限流语义（而非固定 30s 冷却）。
        """
        if not retry_after_header:
            return
        from .retry_policy import AdaptiveRetryStrategy

        seconds = AdaptiveRetryStrategy.delay_from_retry_after(retry_after_header)
        if seconds is not None and seconds > 0:
            self.record_cooldown(provider_id, retry_after_seconds=seconds)

    def record_direct(self, provider_id: str, model_id: str, request_id: str = "") -> None:
        """记录一次「直接路由」决策（selected = requested，不做跨提供商自动降级）。

        供 provider_for 在 healthy/degraded 路径下写入观测记录，前端路由面板据此
        显示该请求真实路由到了请求指定的提供商（reason=direct），而非被自适应偷换。
        """
        with self._lock:
            now = time.time()
            self._record(
                RoutingRecord(
                    ts=now,
                    request_id=request_id,
                    model=model_id,
                    selected_provider=provider_id,
                    requested_provider=provider_id,
                    score=self._calculate_score(provider_id),
                    scores={provider_id: self._calculate_score(provider_id)},
                    reason="direct",
                )
            )

    def record_fallback(self, provider_id: str, model_id: str, requested_provider: str, request_id: str = "") -> None:
        """记录一次「degraded 跨商降级」决策（selected != requested）。

        供 provider_for 在首选 provider 被标记 degraded 时写入观测记录，前端路由面板据此
        显示该请求被降级到能力匹配的健康备用 provider（reason=degraded_fallback），
        而非继续把流量打向降级的首选。与 record_direct 同构（同一 RoutingRecord 字段集）。
        """
        with self._lock:
            now = time.time()
            self._record(
                RoutingRecord(
                    ts=now,
                    request_id=request_id,
                    model=model_id,
                    selected_provider=provider_id,
                    requested_provider=requested_provider,
                    score=self._calculate_score(provider_id),
                    scores={
                        provider_id: self._calculate_score(provider_id),
                        requested_provider: self._calculate_score(requested_provider),
                    },
                    reason="degraded_fallback",
                )
            )

    # ── 核心打分 ──
    def _calculate_score(self, pid: str) -> float:
        st = self.nodes.setdefault(pid, ProviderNodeStats(provider_id=pid))
        total = st.success_count + st.failure_count
        # Laplace 平滑成功率（冷启动不偏 0/1）
        success_rate = (st.success_count + 1.0) / (total + 2.0)
        latency_factor = math.log10(max(_LATENCY_FLOOR, st.ewma_latency_ms))
        load_penalty = 1.0 / (1.0 + 0.1 * st.in_flight_requests)
        return (success_rate / latency_factor) * load_penalty

    def _snapshot_scores(self, candidates: list[str]) -> dict[str, float]:
        return {pid: self._calculate_score(pid) for pid in candidates}

    # ── v8.0 P1-3: Thompson Sampling + UCB1 ──────────────────────
    _THOMPSON_MIN_SAMPLES = 5  # 样本 >= 此值切 Thompson，否则 UCB1 冷启动

    def _select_thompson(self, candidates: list[str]) -> str:
        """Thompson Sampling：从 Beta(alpha,beta) 后验采样，选采样值最大的候选。

        Beta 分布后验采样 = 成功率的概率分布抽样，自然平衡探索/利用：
        - 高成功率 provider 后验集中高值，大概率被选（利用）
        - 低样本 provider 后验方差大，偶尔被选（探索）
        负载惩罚二次过滤：采样 top-K 后用 _calculate_score 选（避免选到 in_flight 过高的）。
        """
        import random as _random

        samples = {}
        for pid in candidates:
            st = self.nodes.setdefault(pid, ProviderNodeStats(provider_id=pid))
            # Beta(alpha, beta) 采样：alpha/beta 均 >=1（Laplace 平滑），用 random.betavariate
            samples[pid] = _random.betavariate(max(1.0, st.alpha), max(1.0, st.beta))
        # 二次过滤：采样值 top-2 中按负载惩罚选（防 Thompson 选中过载节点）
        ranked = sorted(candidates, key=lambda pid: samples[pid], reverse=True)
        top = ranked[: min(2, len(ranked))]
        return max(top, key=lambda pid: self._calculate_score(pid))

    def _select_ucb1(self, candidates: list[str]) -> str:
        """UCB1 冷启动：置信上界选 provider，样本少时强探索。

        UCB1 = success_rate + sqrt(2 * ln(total_pulls) / n_i)
        - n_i 小（少样本）→ 置信上界大 → 强制探索
        - total_pulls=0 时（全冷启动）随机选（防 ln(0)）
        """
        import random as _random

        total_pulls = sum(self.nodes[p].pulls for p in candidates if p in self.nodes)
        if total_pulls == 0:
            return candidates[int(_random.random() * len(candidates))]
        log_n = math.log(max(1, total_pulls))
        best_pid = candidates[0]
        best_ucb = -1.0
        for pid in candidates:
            st = self.nodes.setdefault(pid, ProviderNodeStats(provider_id=pid))
            n_i = max(1, st.pulls)
            success_rate = (st.success_count + 1.0) / (n_i + 2.0)
            ucb = success_rate + math.sqrt(2.0 * log_n / n_i)
            # 负载惩罚二次过滤
            load_penalty = 1.0 / (1.0 + 0.1 * st.in_flight_requests)
            score = ucb * load_penalty
            if score > best_ucb:
                best_ucb = score
                best_pid = pid
        return best_pid

    def _is_available(self, pid: str, now: float) -> tuple[bool, ProviderNodeStats]:
        """检查 provider 是否可用（熔断未开/已恢复 + 未在 CooldownCache 冷却期）。"""
        st = self.nodes.setdefault(pid, ProviderNodeStats(provider_id=pid))
        # v8.1 P1-A5（M10）：CooldownCache 冷却期内不可用（与 circuit_state 互补）
        if st.cooldown_until > now:
            return False, st
        if st.circuit_state == "OPEN":
            if now >= st.circuit_open_until:
                st.circuit_state = "HALF_OPEN"
                return True, st
            return False, st
        return True, st

    def select_best(
        self,
        candidates: list[str],
        *,
        request_id: str = "",
        model: str = "",
        requested_provider: str = "",
        explore: bool | None = None,
    ) -> str:
        """从候选 provider 中选出路由目标。

        生产调用语义（P1-1 修正）：
        - healthy 路径**不**调用本方法——registry.provider_for healthy 分支直接返回
          请求指定的提供商（model_id 前缀即提供商），保证用户指定的 nanobanana/
          aifreeforever 等模型真实路由到对应提供商，不被自动路由偷换。
        - 仅 registry.provider_for degraded 多候选降级路径调用本方法：当首选
          provider degraded 且存在 ≥2 个能力匹配的健康备用时，在备选间 MAB-EWMA
          打分选最优（MAB 投资变现）；单候选不调用（单候选无打分意义）。
        - 全熔断兜底：所有候选均 OPEN 时返回首个候选（最坏也只是慢，不卡死）。

        候选应为健康/或已从熔断恢复的 provider。返回选中的 provider_id，
        并写入一条路由记录（request_id/model 便于前端追踪）。
        """
        requested_provider = requested_provider or (candidates[0] if candidates else "")
        if not candidates:
            raise ValueError("select_best 需要至少一个候选")
        now = time.time()

        with self._lock:
            valid = []
            for pid in candidates:
                ok, _ = self._is_available(pid, now)
                if ok:
                    valid.append(pid)
            if not valid:
                # 全部熔断 → 兜底：返回第一个候选（最坏也只是慢，不卡死）
                scores = self._snapshot_scores(candidates)
                picked = candidates[0]
                self._record(
                    RoutingRecord(
                        ts=now,
                        request_id=request_id,
                        model=model,
                        selected_provider=picked,
                        requested_provider=requested_provider,
                        score=scores.get(picked, 0.0),
                        scores=scores,
                        reason="fallback_all_open",
                    )
                )
                self._record_inflight_locked(picked)
                return picked

            # v8.0 P1-3：Thompson Sampling + UCB1 替代 Epsilon-Greedy
            # 冷启动（总样本 < 阈值）用 UCB1 强探索；样本充足切 Thompson 后验采样
            sample_total = sum(
                self.nodes[p].success_count + self.nodes[p].failure_count for p in valid if p in self.nodes
            )
            if explore is False:
                # 测试/确定性路径：强制选最高分（不探索）
                scores = self._snapshot_scores(valid)
                picked = max(valid, key=lambda pid: scores[pid])
                reason = "best_score"
            elif sample_total < self._THOMPSON_MIN_SAMPLES:
                # 冷启动：UCB1 强探索
                picked = self._select_ucb1(valid)
                reason = "ucb1_explore"
                scores = self._snapshot_scores(valid)
            else:
                # 样本充足：Thompson Sampling 后验采样 + 负载惩罚
                picked = self._select_thompson(valid)
                reason = "thompson"
                scores = self._snapshot_scores(valid)
            self._record(
                RoutingRecord(
                    ts=now,
                    request_id=request_id,
                    model=model,
                    selected_provider=picked,
                    requested_provider=requested_provider,
                    score=scores.get(picked, 0.0),
                    scores=scores,
                    reason=reason,
                )
            )
            self._record_inflight_locked(picked)
            return picked

    def _record_inflight_locked(self, pid: str) -> None:
        st = self.nodes.setdefault(pid, ProviderNodeStats(provider_id=pid))
        st.in_flight_requests += 1
        st.pulls += 1  # v8.0 P1-3: UCB1 全局计数

    @staticmethod
    def _rand() -> float:
        import random as _random

        return _random.random()

    # ── 面板 ──
    def node_snapshot(self) -> dict[str, dict]:
        """所有 provider 的统计快照（前端路由面板展示）。"""
        with self._lock:
            return {
                pid: {
                    "provider_id": pid,
                    "success_count": st.success_count,
                    "failure_count": st.failure_count,
                    "ewma_latency_ms": round(st.ewma_latency_ms, 1),
                    "in_flight_requests": st.in_flight_requests,
                    "circuit_state": st.circuit_state,
                    "circuit_open_until": st.circuit_open_until,
                    "consecutive_failures": st.consecutive_failures,
                    "score": round(self._calculate_score(pid), 4),
                    "alpha": st.alpha,  # v8.0 P1-3: Thompson Beta 参数
                    "beta": st.beta,  # v8.0 P1-3: Thompson Beta 参数
                    "pulls": st.pulls,  # v8.0 P1-3: UCB1 计数
                    "cooldown_until": st.cooldown_until,  # v8.1 P1-A5: CooldownCache
                    "retry_after_seconds": st.retry_after_seconds,  # v8.1 P1-A5: Retry-After
                }
                for pid, st in self.nodes.items()
            }

    def reset(self) -> None:
        """清空全部统计（测试 / 运维用）。"""
        with self._lock:
            self.nodes = {}
            self._records = []

    def close(self) -> None:
        """关闭持久化连接（进程退出 / 测试收尾用）。"""
        if self._store is not None:
            self._store.close()
            self._store = None


def _default_routing_db_path() -> str:
    """读取配置的路由持久化文件路径；未配置/读取失败返回空串（关闭）。"""
    try:
        from . import config

        return getattr(config, "IF_ROUTING_DB", "") or ""
    except Exception:
        return ""


# 模块级单例（registry 启动时挂载；IF_ROUTING_DB 配置时启用持久化）
adaptive_router = AdaptiveRouter(db_path=_default_routing_db_path())
