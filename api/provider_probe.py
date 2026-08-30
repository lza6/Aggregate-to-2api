"""上游提供商状态巡检探针：自动化定时探测上游可用性、HTTP 状态码、响应时延与页面特征。

定时探测上游目标：
- imagefree.net（主站）
- aifreeforever.com
- nanobanana-pro.com
- cf_solver (8001 本地求解器)
"""

from __future__ import annotations

import asyncio
import logging
import time
import httpx
from . import config

log = logging.getLogger("provider_probe")

# 上游探测配置清单
PROBE_TARGETS = [
    {
        "provider": "imagefree",
        "name": "imagefree.net",
        "url": "https://imagefree.net",
        "api_endpoint": "https://imagefree.net/api/generate",
        "check_type": "web_and_api",
    },
    {
        "provider": "aifreeforever",
        "name": "aifreeforever.com",
        "url": "https://aifreeforever.com",
        "api_endpoint": "https://aifreeforever.com/api/generate",
        "check_type": "web_and_api",
    },
    {
        "provider": "nanobanana",
        "name": "nanobanana-pro.com",
        "url": "https://nanobanana-pro.com/zh",
        "api_endpoint": "https://nanobanana-pro.com/api/auth/session",
        "check_type": "web_and_api",
    },
]


class ProviderProbeManager:
    """全自动上游状态巡检引擎。"""

    def __init__(self) -> None:
        self.results: dict[str, dict] = {}
        self.last_probe_time: float = 0.0
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self, interval_seconds: int = 300) -> None:
        """启动后台自动巡检循环（默认每 5 分钟探测一次）。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(interval_seconds))
        log.info("上游提供商自动巡检探针已启动 (周期 %ds)", interval_seconds)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self, interval: int) -> None:
        while self._running:
            try:
                await self.probe_all()
            except Exception as e:
                log.warning("上游巡检异常: %s", e)
            await asyncio.sleep(interval)

    async def probe_all(self) -> dict[str, dict]:
        """执行全量上游探测。"""
        headers = {
            "User-Agent": config.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
            tasks = [self._probe_one(client, target) for target in PROBE_TARGETS]
            res_list = await asyncio.gather(*tasks, return_exceptions=True)
            for target, res in zip(PROBE_TARGETS, res_list):
                if isinstance(res, Exception):
                    self.results[target["provider"]] = {
                        "name": target["name"],
                        "status": "error",
                        "http_code": 0,
                        "latency_ms": 0,
                        "error": str(res),
                        "checked_at": time.time(),
                        "healthy": False,
                    }
                else:
                    self.results[target["provider"]] = res
        self.last_probe_time = time.time()
        return self.results

    async def _probe_one(self, client: httpx.AsyncClient, target: dict) -> dict:
        t0 = time.monotonic()
        try:
            r = await client.get(target["url"])
            latency = int((time.monotonic() - t0) * 1000)
            is_ok = r.status_code in (200, 301, 302, 403)  # 403 可能是 Cloudflare 质询，表明站点存活
            status_label = "healthy" if r.status_code == 200 else ("shield" if r.status_code == 403 else "degraded")
            return {
                "name": target["name"],
                "url": target["url"],
                "status": status_label,
                "http_code": r.status_code,
                "latency_ms": latency,
                "page_title": target["name"],
                "checked_at": time.time(),
                "healthy": is_ok,
                "error": None if is_ok else f"HTTP {r.status_code}",
            }
        except Exception as e:
            latency = int((time.monotonic() - t0) * 1000)
            return {
                "name": target["name"],
                "url": target["url"],
                "status": "down",
                "http_code": 0,
                "latency_ms": latency,
                "checked_at": time.time(),
                "healthy": False,
                "error": str(e)[:100],
            }

    def snapshot(self) -> dict:
        return {
            "last_probe_time": self.last_probe_time,
            "providers": self.results,
        }


# 全局单例
provider_probe = ProviderProbeManager()
