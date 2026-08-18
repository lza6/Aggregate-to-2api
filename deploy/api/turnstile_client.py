"""cf_solver 客户端：求解 Cloudflare Turnstile token。

契约（见 cf_solver/README.md）：
  GET /turnstile?url=&sitekey=  → 202 {task_id, status:"accepted"}
  GET /result?id=<task_id>      → 200 {status:"success", value:<token>}
                                → 202 处理中 / 404 过期 / 408 超时 / 422 失败

H2: 共享单个 httpx.AsyncClient（连接池复用），避免每次求解新建连接。
"""
import asyncio
import logging
import time

import httpx

from . import config
# 注意：solver_guard 模块内定义了同名单例实例，须导入实例本身（`from . import solver_guard`
# 会绑到模块对象，`solver_guard.record_success()` 将 AttributeError）。
from .solver_guard import solver_guard

log = logging.getLogger("turnstile")

# 结果轮询间隔：真实 cf_solver 求解 ~5s，2s 轮询合理；mock/CI 求解极快时可经配置调小。
POLL_INTERVAL = config.TURNSTILE_POLL_INTERVAL


class TurnstileError(RuntimeError):
    pass


class _SolverRejected(TurnstileError):
    """cf_solver 明确判定求解失败（captcha_fail），区别于 HTTP 终态错误。"""


# ── 共享连接池（H2）─────────────────────────────────
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """惰性创建共享 client：复用连接，避免每任务 TLS 握手。"""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            proxy=config.PROXY,
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
    cf_solver_url: str,
    url: str,
    sitekey: str,
    timeout: float,
    proxy: str | None = None,
) -> tuple[str, float]:
    """求解并返回 (token, 求解耗时秒数)；失败抛 TurnstileError/TimeoutError。

    连接走模块级共享 client（H2，创建时绑定 config.PROXY），不逐调用新建。
    proxy 参数：指定出口代理（如住宅代理池的某个会话）。cf_solver 会用该代理解 token，
    解出的 token 与代理 IP 绑定，提交时必须用同一代理（图生图绕过上游并发=1 的会话绑定）。

    所有求解路径在此统一上报 solver_guard（成功/失败/耗时/原因），驱动熔断与健康指标。
    返回的耗时用于 _TokenPool 的 EMA 自适应延迟计算（IMP-02）。
    """
    t0 = time.monotonic()
    try:
        token = await _solve_turnstile(cf_solver_url, url, sitekey, timeout, proxy)
    except asyncio.TimeoutError:
        solver_guard.record_failure("timeout", time.monotonic() - t0)
        raise
    except _SolverRejected:
        solver_guard.record_failure("solver_rejected", time.monotonic() - t0)
        raise
    except TurnstileError:
        solver_guard.record_failure("http_error", time.monotonic() - t0)
        raise
    except httpx.TransportError:
        solver_guard.record_failure("transport", time.monotonic() - t0)
        raise
    except Exception:
        solver_guard.record_failure("other", time.monotonic() - t0)
        raise
    else:
        duration = time.monotonic() - t0
        solver_guard.record_success(duration)
        return token, duration


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
    r = await client.get(f"{cf_solver_url}/turnstile", params=params,
                         timeout=httpx.Timeout(timeout))
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
            res = await client.get(f"{cf_solver_url}/result", params={"id": task_id},
                                   timeout=httpx.Timeout(30))
        except httpx.TransportError as e:
            log.warning("cf_solver 请求异常: %s", e)
            await asyncio.sleep(POLL_INTERVAL)
            continue

        data = res.json()

        if res.status_code == 200:  # success
            token = data.get("value")
            if token and token != "captcha_fail":
                log.info("turnstile 求解成功 (%.1fs)", data.get("elapsed_time", 0))
                return token
            raise _SolverRejected(f"turnstile 求解失败: {data}")

        if res.status_code in (404, 408, 422):  # 终态错误
            raise TurnstileError(f"turnstile 求解失败: HTTP {res.status_code} {data}")

        # 202 处理中
        await asyncio.sleep(POLL_INTERVAL)
