"""cf_solver 客户端：求解 Cloudflare Turnstile token，集成分布式求解节点调度与故障转移。

契约（见 cf_solver/README.md）：
  GET /turnstile?url=&sitekey=  → 202 {task_id, status:"accepted"}
  GET /result?id=<task_id>      → 200 {status:"success", value:<token>}
                                → 202 处理中 / 404 过期 / 408 超时 / 422 失败 / 429 限流

H2: 共享单个 httpx.AsyncClient（连接池复用），避免每次求解新建连接。
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from . import config
from .solver_guard import solver_guard
from .telemetry import get_tracer

log = logging.getLogger("turnstile")

# 结果轮询间隔：真实 cf_solver 求解 ~5s，2s 轮询合理；mock/CI 求解极快时可经配置调小。
POLL_INTERVAL = config.TURNSTILE_POLL_INTERVAL


class TurnstileError(RuntimeError):
    pass


class TurnstileRateLimited(TurnstileError):
    """cf_solver 返回 429 Too Many Requests 限流。"""

    pass


class _SolverRejected(TurnstileError):
    """cf_solver 明确判定求解失败（captcha_fail），区别于 HTTP 终态错误。"""

    pass


# ── 共享连接池（H2）─────────────────────────────────
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """惰性创建共享 client：复用连接，避免每任务 TLS 握手。"""
    global _client
    if _client is None:
        # 空串代理（IF_PROXY="" 等）会被 httpx 拒绝：Unknown scheme for proxy URL
        proxy = (
            config.PROXY if (isinstance(config.PROXY, str) and config.PROXY.strip()) or config.PROXY is None else None
        )
        if isinstance(proxy, str) and not proxy.strip():
            proxy = None
        _client = httpx.AsyncClient(
            proxy=proxy,
            timeout=httpx.Timeout(30.0),
            headers={"User-Agent": config.USER_AGENT},
            limits=httpx.Limits(
                max_keepalive_connections=config.IF_HTTP_KEEPALIVE,
                max_connections=config.IF_HTTP_MAX_CONNECTIONS,
            ),
        )
    return _client


async def close_client() -> None:
    """服务停止时关闭共享连接池。"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def solve_turnstile(
    cf_solver_url: str | None = None,
    url: str = "",
    sitekey: str = "",
    timeout: float = 90.0,
    proxy: str | None = None,
) -> tuple[str, float]:
    """求解并返回 (token, 求解耗时秒数)；失败抛 TurnstileError/TimeoutError。

    支持分布式节点池调度与故障自动转移 (failover)：
    - 若传入 cf_solver_url，以此为主；
    - 若 cf_solver_url 为空，由 solver_guard 自动选举最优负载节点；
    - 当遇到 429 限流或网络 transport 错误时，对当前节点熔断并自动尝试下一个备选节点。
    """
    tracer = get_tracer()
    t0 = time.monotonic()
    deadline = t0 + timeout

    explicit_single_node = bool(cf_solver_url and cf_solver_url.strip())

    # 确定候选节点列表
    candidate_urls: list[str] = []
    if explicit_single_node and cf_solver_url:
        base_target = cf_solver_url.rstrip("/")
        candidate_urls.append(base_target)
        # 获取其他集群节点作为 failover 备选
        for n in solver_guard.select_candidates(exclude_urls={base_target}):
            candidate_urls.append(n.url)
    else:
        candidates = solver_guard.select_candidates()
        if not candidates:
            selected = solver_guard.select_node()
            candidate_urls = [selected.url] if selected else [config.CF_SOLVER_URL.rstrip("/")]
        else:
            candidate_urls = [n.url for n in candidates]

    last_exc: Exception | None = None

    with tracer.start_as_current_span(
        "turnstile.solve",
        attributes={
            "target.url": url,
            "sitekey": sitekey[:12] + "...",
            "proxy": "yes" if proxy else "no",
        },
    ):
        for idx, target_node in enumerate(candidate_urls):
            remaining_timeout = deadline - time.monotonic()
            if remaining_timeout <= 0:
                break

            # 标记节点 inflight（通过公共方法，避免直接访问 solver_guard._nodes）
            node_state = solver_guard.acquire_inflight_for(target_node)

            node_t0 = time.monotonic()
            try:
                token = await _solve_turnstile(target_node, url, sitekey, remaining_timeout, proxy)
                duration = time.monotonic() - node_t0
                solver_guard.record_success(duration, node_url=target_node)
                total_duration = time.monotonic() - t0
                return token, total_duration
            except TurnstileRateLimited as e:
                dur = time.monotonic() - node_t0
                solver_guard.record_failure("rate_limit", dur, node_url=target_node)
                log.warning("求解节点 [%s] 返回 429 限流，触发熔断并切换备用节点", target_node)
                last_exc = e
            except asyncio.TimeoutError as e:
                dur = time.monotonic() - node_t0
                solver_guard.record_failure("timeout", dur, node_url=target_node)
                last_exc = e
            except _SolverRejected as e:
                dur = time.monotonic() - node_t0
                solver_guard.record_failure("solver_rejected", dur, node_url=target_node)
                last_exc = e
                # 求解被 captcha_fail 拒绝通常为特征/IP风控，直接抛出
                raise
            except httpx.TransportError as e:
                dur = time.monotonic() - node_t0
                solver_guard.record_failure("transport", dur, node_url=target_node)
                log.warning("求解节点 [%s] 网络异常: %s, 切换备用节点", target_node, e)
                last_exc = e
            except TurnstileError as e:
                dur = time.monotonic() - node_t0
                solver_guard.record_failure("http_error", dur, node_url=target_node)
                last_exc = e
                # 业务终态报错（如 404/422/503），在单节点测试或无其他候选时直接抛出
                if explicit_single_node:
                    raise
            except Exception as e:
                dur = time.monotonic() - node_t0
                solver_guard.record_failure("other", dur, node_url=target_node)
                last_exc = e
            finally:
                if node_state:
                    solver_guard.release_inflight_for(target_node)

        # 所有候选节点均尝试完毕仍失败
        if isinstance(last_exc, (TimeoutError, asyncio.TimeoutError)):
            raise TimeoutError("turnstile 求解超时")
        elif last_exc:
            raise last_exc
        else:
            raise TurnstileError("没有可用的 solver 求解节点")


async def _solve_turnstile(
    cf_solver_url: str,
    url: str,
    sitekey: str,
    timeout: float,
    proxy: str | None,
) -> str:
    client = _get_client()
    # 1) 创建求解任务
    params = {"url": url, "sitekey": sitekey}
    if proxy:
        params["proxy"] = proxy

    try:
        r = await client.get(
            f"{cf_solver_url}/turnstile",
            params=params,
            timeout=httpx.Timeout(min(timeout, 30.0)),
        )
    except httpx.TransportError as e:
        raise e

    if r.status_code == 429:
        raise TurnstileRateLimited(f"cf_solver 节点 {cf_solver_url} 触发 429 限流")
    if r.status_code != 202:
        raise TurnstileError(f"cf_solver 创建任务失败: HTTP {r.status_code} {r.text[:200]}")

    body = r.json()
    task_id = body.get("task_id")
    if not task_id:
        raise TurnstileError(f"cf_solver 响应缺少 task_id: {body}")

    # 2) 轮询结果
    deadline = time.monotonic() + timeout
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError("turnstile 求解超时")
        try:
            res = await client.get(
                f"{cf_solver_url}/result",
                params={"id": task_id},
                timeout=httpx.Timeout(30.0),
            )
        except httpx.TransportError as e:
            log.warning("cf_solver 请求异常: %s", e)
            await asyncio.sleep(POLL_INTERVAL)
            continue

        if res.status_code == 429:
            raise TurnstileRateLimited(f"cf_solver 节点 {cf_solver_url} 轮询触发 429 限流")

        data = res.json()

        if res.status_code == 200:  # success
            token = data.get("value")
            if token and token != "captcha_fail":
                log.info("turnstile 求解成功 (%.1fs) 来自 [%s]", data.get("elapsed_time", 0), cf_solver_url)
                return token
            raise _SolverRejected(f"turnstile 求解失败: {data}")

        if res.status_code in (404, 408, 422):  # 终态错误
            raise TurnstileError(f"turnstile 求解失败: HTTP {res.status_code} {data}")

        # 202 处理中
        await asyncio.sleep(POLL_INTERVAL)
