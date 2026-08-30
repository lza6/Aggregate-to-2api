"""免费代理池抓取器：从纯 API 免费源抓取、解析、预检并注入共享 ProxyPool。

低成本住宅代理替代——尤其 aifreeforever「每 IP 每日限额、24h 重置、每请求轮换 IP」
的场景，免费代理量足够大时非常合适。架构（借鉴 chatgpt2api free_proxy_fetcher）：

  asyncio 后台循环 → 多源抓取（proxyscrape / geonode / thespeedx / ercindedeoglu /
  proxy4parsing / monosans / proxifly github，共 13 源）
  → parse_* 解析去重 → TCP 连通性预检 → ProxyPool.add_free()
  → 周期刷新（默认 30 分钟）+ 失效剔除（预检失败的免费代理移出）

安全红线：免费代理无凭据但有数据泄露风险（明文 http）。仅用于图像生成/注册类非敏感调用，
IF_FREE_PROXY 默认关闭（零副作用）；开启才工作。
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
import time

import httpx

from . import config

# 注意：proxy_pool 模块内定义了单例实例 proxy_pool，须导入实例本体
from .proxy_pool import proxy_pool

log = logging.getLogger("free_proxy")

# 抓取超时
FETCH_TIMEOUT = 15.0
# 连通性预检超时（TCP 连接）
PRECHECK_TIMEOUT = 3.0
# 行首 scheme 前缀剥离（proxifly 源行形如 ``socks5://1.2.3.4:1080``）
_SCHEME_PREFIX_RE = re.compile(r"^(?:https?|socks[45]?|socks)://", re.IGNORECASE)

# 免费代理源（name, url, format: ipport|json）
FREE_PROXY_SOURCES = [
    {
        "name": "proxyscrape-v3-http",
        "url": (
            "https://api.proxyscrape.com/v3/free-proxy-list/get?"
            "request=displayproxies&protocol=http&proxy_format=ipport"
            "&format=text&timeout=5000&country=all"
        ),
        "format": "ipport",
    },
    {
        "name": "proxyscrape-v3-ssl",
        "url": (
            "https://api.proxyscrape.com/v3/free-proxy-list/get?"
            "request=displayproxies&protocol=https&proxy_format=ipport"
            "&format=text&timeout=5000&country=all"
        ),
        "format": "ipport",
    },
    {
        "name": "proxyscrape-v3-socks4",
        "url": (
            "https://api.proxyscrape.com/v3/free-proxy-list/get?"
            "request=displayproxies&protocol=socks4&proxy_format=ipport"
            "&format=text&timeout=5000&country=all"
        ),
        "format": "ipport",
    },
    {
        "name": "proxyscrape-v3-socks5",
        "url": (
            "https://api.proxyscrape.com/v3/free-proxy-list/get?"
            "request=displayproxies&protocol=socks5&proxy_format=ipport"
            "&format=text&timeout=5000&country=all"
        ),
        "format": "ipport",
    },
    {
        "name": "proxyscrape-v2",
        "url": (
            "https://api.proxyscrape.com/v2/?request=getproxies"
            "&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"
        ),
        "format": "ipport",
    },
    {
        "name": "geonode",
        "url": (
            "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1"
            "&sort_by=lastChecked&sort_type=desc&protocols=http"
        ),
        "format": "json",
    },
    {
        "name": "proxifly-github",
        "url": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt",
        "format": "ipport",
    },
    # ── 新增 6 个每日更新的纯 ipport 源（GitHub raw，无速率限流硬墙）──
    {
        "name": "thespeedx-http",
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "format": "ipport",
    },
    {
        "name": "ercindedeoglu-http",
        "url": "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/http.txt",
        "format": "ipport",
    },
    {
        "name": "proxy4parsing-http",
        "url": "https://raw.githubusercontent.com/proxy4parsing/proxy-list/main/http.txt",
        "format": "ipport",
    },
    {
        "name": "monosans-http",
        "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "format": "ipport",
    },
    {
        "name": "thespeedx-socks5",
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "format": "ipport",
    },
    {
        "name": "thespeedx-socks4",
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
        "format": "ipport",
    },
]


def _is_valid_public_ip(host: str) -> bool:
    """过滤内网/回环/链路本地/保留/多播地址（H5 安全修复：防恶意代理源注入内网地址）。

    免费代理源只应是公网 IP:port；hostname 一律拒绝（源都是纯 IP）。
    """
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False  # 非合法 IP（hostname 等）→ 拒绝
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def parse_ipport_text(text: str) -> list[str]:
    """解析 ip:port 文本行，返回 url 列表（去重）。仅保留公网 IPv4/IPv6。

    兼容带 scheme 前缀的行（proxifly 源每行形如 ``socks5://1.2.3.4:1080``）：
    先剥掉 ``http://`` / ``https://`` / ``socks5://`` / ``socks4://`` / ``socks://``
    前缀后按 ``ip:port`` 解析，统一注入为 ``http://ip:port``（使用场景一律按 http 代理用，
    真正可用性由后续 ``_precheck`` + 上游 429 反馈决定）。
    """
    seen: set[str] = set()
    out: list[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 剥 scheme 前缀（proxifly 等源行带 socks5:// 前缀）
        line = _SCHEME_PREFIX_RE.sub("", line, count=1)
        if line.count(":") != 1:
            continue
        host, port = line.rsplit(":", 1)
        if not host or not port.isdigit():
            continue
        if not _is_valid_public_ip(host):
            continue
        url = f"http://{host}:{port}"
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def parse_geonode_json(text: str) -> list[str]:
    """解析 geonode JSON（data[].ip/port），返回 url 列表（去重）。仅保留公网 IP。"""
    try:
        data = json.loads(text or "")
    except (ValueError, TypeError):
        return []
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ip = str(item.get("ip") or "").strip()
        port = str(item.get("port") or "").strip()
        if not ip or not port.isdigit():
            continue
        if not _is_valid_public_ip(ip):
            continue
        url = f"http://{ip}:{port}"
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def parse_source(payload: str, fmt: str) -> list[str]:
    if fmt == "ipport":
        return parse_ipport_text(payload)
    if fmt == "json":
        return parse_geonode_json(payload)
    return []


async def _precheck(url: str) -> bool:
    """TCP 连通性预检：能连上代理端口即可用（不做真实转发验证）。"""
    host, _, port = url.partition("://")[2].rpartition(":")
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, int(port)), timeout=PRECHECK_TIMEOUT)
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
        except Exception:
            pass
        return True
    except Exception:
        return False


class FreeProxyFetcher:
    """免费代理后台抓取循环（asyncio 单任务）。"""

    def __init__(self, pool) -> None:
        self.pool = pool
        self.task: asyncio.Task | None = None
        self.stats: dict = {"sources_ok": 0, "fetched": 0, "injected": 0, "last_at": 0.0}
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if not config.FREE_PROXY_ENABLED:
            return
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(FETCH_TIMEOUT), headers={"User-Agent": config.USER_AGENT}, proxy=config.PROXY
        )
        self.task = asyncio.create_task(self._loop())
        log.info("免费代理抓取循环已启动")

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _loop(self) -> None:
        while True:
            try:
                self.stats = await self._fetch_once()
                log.info(
                    "免费代理抓取: sources_ok=%d fetched=%d injected=%d",
                    self.stats["sources_ok"],
                    self.stats["fetched"],
                    self.stats["injected"],
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("免费代理抓取异常: %s", e)
            await asyncio.sleep(config.FREE_PROXY_REFRESH_MIN * 60)

    async def _fetch_once(self) -> dict:
        assert self._client is not None
        sources_ok = fetched = 0
        candidates: list[str] = []
        for src in FREE_PROXY_SOURCES:
            try:
                r = await self._client.get(src["url"])
                if r.status_code != 200:
                    continue
                urls = parse_source(r.text, src["format"])
                if urls:
                    sources_ok += 1
                    fetched += len(urls)
                    candidates.extend(urls)
            except Exception as e:
                log.debug("免费代理源 %s 抓取失败: %s", src["name"], e)
        # 去重 + 预检（并发，限 50 个并行，检查最多 1000 个候选）
        seen: set[str] = set()
        unique = []
        for u in candidates:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        healthy: list[str] = []
        sem = asyncio.Semaphore(50)

        async def _check(u: str) -> bool:
            async with sem:
                return await _precheck(u)

        CHECK_LIMIT = 3000  # 预检上限，匹配 13 源（含 Ercin 6.4 万大源）每天产出的量级
        results = await asyncio.gather(*(_check(u) for u in unique[:CHECK_LIMIT]))
        healthy = [u for u, ok in zip(unique[:CHECK_LIMIT], results) if ok]
        injected = self.pool.add_free(healthy)
        # 失效/过期免费代理剔除
        self.pool.reap_free()
        # L7(审计修复): fetched 只统计实际预检的候选数（与注入口径一致），不虚高
        return {"sources_ok": sources_ok, "fetched": len(unique[:300]), "injected": injected, "last_at": time.time()}


# 模块级单例（main 启动时 start()）
free_proxy_fetcher = FreeProxyFetcher(proxy_pool)
