"""Cloudflare trace 出口探测器：用 cdn-cgi/trace 探测每个免费代理的真实出口 IP/colo。

实测事实（已确认）：
- ``https://one.one.one.one/cdn-cgi/trace`` 文本 ``key=value``（含 ip/colo/loc/uag/http/tls/ts）
- ``https://speed.cloudflare.com/meta`` 需浏览器 UA+Referer（403 风险高，不作为主端点）
- trace 端点返回「发出请求机器的出口信息」，不是传 IP 查归属地。

设计：
- 后台循环（每 ``FREE_PROXY_REFRESH_MIN`` 分钟一轮）；每轮挑「未缓存/超 TTL/最近活跃优先」
  最多 ``IF_PROXY_TRACE_MAX_PER_ROUND`` 个代理，``Semaphore(IF_PROXY_TRACE_CONCURRENCY)``
  并发用 httpx.AsyncClient 挂代理 GET trace 主端点；主端点失败按序换备用
  （cloudflare-dns.com / workers.dev / 1.0.0.1）。
- 结果写 ``_cache``（TTL 1h）+ ``stats``（probed/ok/real_exit/failed/last_at）+ 调
  ``pool.apply_trace_result(url, geo)``。
- ``real_exit`` 的出口 IP 归属地预热进 ``geo_ip._GEO_CACHE``（形状与 guess_country 一致）。
- 假代理处理：``real_exit=False`` 时在 apply_trace_result 里 ``consecutive_fails += 1``
  （不做硬剔除，避免 socks4 假阳性误杀）。
- 模块级单例 ``proxy_tracer = ProxyTracer(proxy_pool)``（延迟绑定 pool，start 时注入）。
- 默认关闭（``IF_PROXY_TRACE_ENABLED=False``），开启才工作（零网络开销）。

安全红线：仅对免费代理探测（住宅代理有凭据，host 即出口）；trace 端点返回的是「出口 IP」，
不是用户真实 IP，无隐私泄露风险。Mock 场景覆盖：success / 403 / 超时 / 主端点失败换备用。
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from . import config
from .geo_ip import COUNTRY_NAMES, _GEO_CACHE

log = logging.getLogger("proxy_tracer")

# trace 端点：主 + 备用（主端点失败按序换备用）
TRACE_ENDPOINTS = [
    "https://one.one.one.one/cdn-cgi/trace",
    "https://cloudflare-dns.com/cdn-cgi/trace",
    "https://1.0.0.1/cdn-cgi/trace",
    "https://workers.dev/cdn-cgi/trace",
]
# 探测超时（挂代理请求 trace，3s 足够；代理慢则失败换备用）
TRACE_TIMEOUT = 3.0


def _parse_trace(text: str) -> dict:
    """解析 trace 文本（``key=value`` 每行）为 dict。

    非法行/空行跳过；value 保留原始字符串。例::

        ip=1.2.3.4\\ncolo=SJC\\nloc=US\\nhttp=HTTP/2\\ntls=TLSv1.3\\nts=...
    """
    out: dict[str, str] = {}
    if not text:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if k:
            out[k] = v.strip()
    return out


def _extract_host(url: str) -> str:
    """从代理 url（``http://1.2.3.4:80`` 或 ``http://user:pass@host:port``）提取 host。"""
    from urllib.parse import urlsplit
    try:
        u = urlsplit(url)
        return u.hostname or url
    except (ValueError, TypeError):
        return url


def _trace_to_geo(host: str, t: dict) -> dict:
    """将 trace dict 转成 geo 信息（形状与 geo_ip.guess_country 兼容）。

    - exit_ip: trace 返回的真实出口 IP（``ip=...``）
    - real_exit: exit_ip 非空且 != host → 代理转发成功（出口不同）
    - colo: Cloudflare 数据中心代码（``colo=SJC``）
    - code/name/emoji/desc: 按 colo/loc 解析国家（复用 COUNTRY_NAMES）
    - ts/http/tls: 透传 trace 元数据
    """
    exit_ip = str(t.get("ip") or "").strip()
    real_exit = bool(exit_ip) and exit_ip != host
    colo = str(t.get("colo") or "").strip()
    loc = str(t.get("loc") or "").strip()
    # 优先用 loc（国家代码），其次 colo 首字母兜底（colo 不直接映射国家）
    code = loc or "UN"
    cname, emoji = COUNTRY_NAMES.get(code, ("未知", "🌐"))
    return {
        "exit_ip": exit_ip,
        "real_exit": real_exit,
        "colo": colo,
        "code": code,
        "name": cname,
        "emoji": emoji,
        "desc": f"{cname} · Cloudflare {colo}" if colo else cname,
        "ts": float(t.get("ts") or 0.0) or time.time(),
        "http": str(t.get("http") or ""),
        "tls": str(t.get("tls") or ""),
    }


class ProxyTracer:
    """Cloudflare trace 出口探测器（asyncio 后台单任务）。

    生命周期由 lifespan 管理：``IF_PROXY_TRACE_ENABLED=True`` 时在 free_proxy_fetcher.start()
    之后启动；stop 放在「⑤ 代理/号池停止」阶段。
    """

    def __init__(self, pool) -> None:
        self.pool = pool
        self.task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None
        self._cache: dict[str, dict] = {}  # url -> geo（TTL=IF_PROXY_TRACE_TTL）
        self.stats: dict = {
            "probed": 0, "ok": 0, "real_exit": 0, "failed": 0, "last_at": 0.0,
        }

    async def start(self) -> None:
        """启动后台探测循环（``IF_PROXY_TRACE_ENABLED=False`` 时直接返回）。"""
        if not config.IF_PROXY_TRACE_ENABLED:
            return
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(TRACE_TIMEOUT),
            headers={"User-Agent": config.USER_AGENT},
        )
        self.task = asyncio.create_task(self._loop())
        log.info("Cloudflare trace 探测循环已启动")

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _loop(self) -> None:
        """后台循环：每 ``FREE_PROXY_REFRESH_MIN`` 分钟一轮探测。"""
        while True:
            try:
                self.stats = await self._probe_once()
                log.info(
                    "trace 探测: probed=%d ok=%d real_exit=%d failed=%d",
                    self.stats["probed"], self.stats["ok"],
                    self.stats["real_exit"], self.stats["failed"],
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("trace 探测异常: %s", e)
            await asyncio.sleep(config.FREE_PROXY_REFRESH_MIN * 60)

    def _pick_targets(self) -> list[str]:
        """挑选本轮探测目标：未缓存/超 TTL 的免费代理，最近活跃优先，最多 ``MAX_PER_ROUND``。"""
        if not self.pool or not self.pool.entries:
            return []
        now = time.time()
        ttl = config.IF_PROXY_TRACE_TTL
        max_per_round = config.IF_PROXY_TRACE_MAX_PER_ROUND
        candidates: list[tuple[float, str]] = []
        for e in self.pool.entries:
            if getattr(e, "source", "") != "free":
                continue  # 仅探测免费代理（住宅代理有凭据，host 即出口）
            cached = self._cache.get(e.url)
            if cached and now - cached.get("ts", 0) < ttl:
                continue  # 缓存未过期
            # 最近活跃优先：last_used_at 越大越优先；未用过取 added_at
            rank = getattr(e, "last_used_at", 0.0) or getattr(e, "added_at", 0.0)
            candidates.append((rank, e.url))
        # 按活跃度降序，取前 max_per_round
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [url for _, url in candidates[:max_per_round]]

    async def _fetch_trace(self, proxy_url: str) -> dict | None:
        """挂代理请求 trace 主端点；主端点失败按序换备用。返回解析后的 trace dict 或 None。

        httpx 0.28：proxy 在 AsyncClient 构造期注入（per-request proxy 已废弃），
        故为每个代理临时建 client（探测完即关）。trust_env=False 防止读环境变量代理。
        """
        for endpoint in TRACE_ENDPOINTS:
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(TRACE_TIMEOUT),
                    proxy=proxy_url,
                    trust_env=False,
                    headers={"User-Agent": config.USER_AGENT},
                ) as cli:
                    r = await cli.get(endpoint)
                    if r.status_code != 200:
                        continue
                    t = _parse_trace(r.text)
                    if t.get("ip"):
                        return t
            except (httpx.HTTPError, OSError):
                continue
        return None

    async def _probe_once(self) -> dict:
        """一轮探测：挑目标 → 并发挂代理请求 trace → 回填 pool + 预热 geo cache。"""
        targets = self._pick_targets()
        if not targets:
            return {**self.stats, "last_at": time.time()}
        sem = asyncio.Semaphore(config.IF_PROXY_TRACE_CONCURRENCY)
        probed = ok = real_exit = failed = 0

        async def _probe_one(url: str) -> None:
            nonlocal probed, ok, real_exit, failed
            async with sem:
                host = _extract_host(url)
                t = await self._fetch_trace(url)
                probed += 1
                if not t:
                    failed += 1
                    return
                geo = _trace_to_geo(host, t)
                ok += 1
                if geo["real_exit"]:
                    real_exit += 1
                # 写缓存
                self._cache[url] = geo
                # 回填 pool（apply_trace_result 内部加锁）
                await self.pool.apply_trace_result(url, geo)
                # real_exit 的出口 IP 归属地预热进 geo_ip._GEO_CACHE
                if geo["real_exit"] and geo["exit_ip"]:
                    cached = {
                        "code": geo["code"],
                        "name": geo["name"],
                        "desc": geo["desc"],
                        "emoji": geo["emoji"],
                    }
                    if len(_GEO_CACHE) < 10000:
                        _GEO_CACHE[geo["exit_ip"]] = cached

        await asyncio.gather(*(_probe_one(u) for u in targets))
        return {
            "probed": probed, "ok": ok, "real_exit": real_exit,
            "failed": failed, "last_at": time.time(),
        }


# 模块级单例（lifespan 启动时按 IF_PROXY_TRACE_ENABLED start/stop）
proxy_tracer = ProxyTracer(None)  # type: ignore[arg-type]
