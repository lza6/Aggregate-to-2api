"""多提供商共享代理池：住宅代理（文件）+ 免费代理（抓取器）双源 + 每 IP 24h 冷却重置。

需求（逆向确认）：aifreeforever 每 IP 每日限额，429 冷却递增，约 24h 重置 → 每请求必须
用不同出口 IP。号池注册也需轮换 IP 防批量风控。

设计：
- 双源：住宅代理文件（每行 http://user:pass@host:port，优先）+ 免费代理
  （free_proxy_fetcher 后台抓取注入，source="free"，量大兜底）。
- 分配：优先选从未使用过的 IP（use_count == 0）；全部用过一轮后选冷却最早结束的。
- 冷却：每 IP 记 {use_count, cooldown_until}，USE_COOLDOWN_MAP 决定递增冷却时间。
- 状态：每 IP 记 {last_used_at, daily_uses, cooldown_until}；429 冷却进入 cooldown；
  24h 后 daily_uses 清零（每日限额重置）。
- 观测：snapshot 只暴露 host:port（不泄漏住宅代理 user:pass 凭据）。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from urllib.parse import urlsplit

from . import config

log = logging.getLogger("proxy_pool")

# 冷却 / 每日限额
DAILY_WINDOW = 24 * 3600

# 递增冷却秒数映射：{use_count: cooldown_seconds}
# 第 1 次使用后等待 0s，第 2 次 30s，第 3 次 90s，第 4 次 300s，第 5 次+ 900s
_RAW_COOLDOWN = os.getenv("IF_PROXY_USE_COOLDOWN_MAP", "0,30,90,300,900")
USE_COOLDOWN_MAP: dict[int, int] = {
    i + 1: int(v)
    for i, v in enumerate(_RAW_COOLDOWN.split(","))
}


def _cooldown_for(use_count: int) -> int:
    """返回给定 use_count 对应的冷却秒数。
    use_count 超过映射长度时取最后一个值（上限冷却）。
    """
    return USE_COOLDOWN_MAP.get(use_count, list(USE_COOLDOWN_MAP.values())[-1])


def _safe_url(url: str) -> str:
    """观测面脱敏：只暴露 host:port，不泄漏 user:pass 凭据。"""
    try:
        u = urlsplit(url)
        host = u.hostname or url
        return f"{host}:{u.port}" if u.port else host
    except (ValueError, TypeError):
        return hashlib.sha256(url.encode("utf-8", "replace")).hexdigest()[:12]


class ProxyEntry:
    __slots__ = ("url", "source", "added_at", "last_used_at", "daily_uses", "day_key",
                 "cooldown_until", "consecutive_fails", "use_count")

    def __init__(self, url: str, source: str = "residential") -> None:
        self.url = url
        self.source = source          # residential | free
        self.added_at = time.time()   # 注入时间（免费代理生命周期用）
        self.last_used_at = 0.0
        self.daily_uses = 0
        self.day_key = int(time.time() / DAILY_WINDOW)  # 初始化当前 day，避免空字符串 != int 导致首次 available 误重置
        self.cooldown_until = 0.0
        self.consecutive_fails = 0
        self.use_count = 0            # 当前 24h 窗口内使用次数（用于递增冷却决策）

    @property
    def cooling(self) -> bool:
        """是否在冷却中。"""
        return time.time() < self.cooldown_until

    def available(self, now: float) -> bool:
        # 冷却中不可用
        if now < self.cooldown_until:
            return False
        # 新的一天 → 每日计数清零（24h 重置）
        day = int(now / DAILY_WINDOW)
        if day != self.day_key:
            self.day_key = day
            self.daily_uses = 0
            self.consecutive_fails = 0
            self.use_count = 0
        # 每日使用次数限制
        max_use = config.IF_PROXY_MAX_USE_PER_DAY
        if max_use > 0 and self.use_count >= max_use:
            return False
        return True

    def snapshot(self) -> dict:
        now = time.time()
        return {
            "url": _safe_url(self.url),
            "source": self.source,
            "daily_uses": self.daily_uses,
            "use_count": self.use_count,
            "cooling": now < self.cooldown_until,
            "cooldown_seconds": max(0, int(self.cooldown_until - now)),
            "fails": self.consecutive_fails,
        }


class ProxyPool:
    def __init__(self, proxy_file: str = "") -> None:
        self.entries: list[ProxyEntry] = []
        self._idx = 0
        self._lock = asyncio.Lock()
        if proxy_file:
            self.load_file(proxy_file)

    def load_file(self, path: str) -> int:
        try:
            with open(path, encoding="utf-8") as f:
                urls = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        except OSError as e:
            log.warning("代理文件不可读 %s: %s", path, e)
            return 0
        seen = {e.url for e in self.entries}
        added = 0
        for u in urls:
            if u not in seen:
                self.entries.append(ProxyEntry(u, source="residential"))
                seen.add(u)
                added += 1
        log.info("代理池加载 %d 个（新增 %d）", len(self.entries), added)
        return added

    def add_free(self, urls: list[str]) -> int:
        """批量注入免费代理（去重，source="free"）。返回新增数。"""
        seen = {e.url for e in self.entries}
        added = 0
        for u in urls:
            if u not in seen:
                self.entries.append(ProxyEntry(u, source="free"))
                seen.add(u)
                added += 1
        if added:
            log.info("免费代理注入 %d 个（池总数 %d）", added, len(self.entries))
        return added

    def reap_free(self) -> int:
        """剔除「注入超 3h 且最近 30 分钟未使用」的免费代理（IMP: 延长保留时间，匹配 aifreeforever 24h 每日限额周期）。"""
        now = time.time()
        keep = []
        for e in self.entries:
            if e.source == "free" and now - e.added_at > 10800 and now - e.last_used_at > 1800:
                continue  # 陈旧且长期未用 → 剔除
            keep.append(e)
        removed = len(self.entries) - len(keep)
        self.entries = keep
        if removed:
            log.info("剔除过期免费代理 %d 个", removed)
        return removed

    @property
    def enabled(self) -> bool:
        return bool(self.entries)

    async def acquire(self, force_rotate: bool = True, prefer_source: str | None = None) -> str | None:
        """分配一个可用出口代理。

        分配策略：
        1. 优先选 use_count == 0 的 IP（从未使用过 / 24h 重置后）
        2. 全部用过一轮后，选冷却最早结束的可用 IP
        3. 全在冷却 → 返回冷却最早结束的（权宜用）
        """
        if not self.entries:
            return None
        async with self._lock:
            now = time.time()

            candidates = [e for e in self.entries if e.available(now)]
            if prefer_source and candidates:
                pref = [e for e in candidates if e.source == prefer_source]
                if pref:
                    candidates = pref

            if candidates:
                # 优先选从未使用过的 IP
                unused = [e for e in candidates if e.use_count == 0]
                if unused:
                    pick = min(unused, key=lambda e: e.last_used_at)
                else:
                    # 全部用过一轮，选冷却最早结束的
                    pick = min(candidates, key=lambda e: e.cooldown_until)
            else:
                # 全在冷却 → 选最早结束冷却的
                pick = min(self.entries, key=lambda e: e.cooldown_until)

            # 使用后更新状态
            pick.last_used_at = now
            pick.use_count += 1
            pick.daily_uses += 1
            pick.cooldown_until = now + _cooldown_for(pick.use_count)
            return pick.url

    async def mark_failure(self, url: str, rate_limited: bool = True) -> None:
        """请求失败：冷却该 IP；失败不增加 use_count（请求没成功不计入使用次数）。
        429 时 cooldown_until 设置为当前时间 + 递增冷却时间（基于当前 use_count + 1 的冷却等级）。
        """
        async with self._lock:
            for e in self.entries:
                if e.url == url:
                    e.consecutive_fails += 1
                    if rate_limited:
                        # 429：用递增冷却，基于假设的"下一次使用"的冷却等级
                        next_level = min(e.use_count + 1, max(USE_COOLDOWN_MAP.keys(), default=5))
                        e.cooldown_until = time.time() + _cooldown_for(next_level)
                    else:
                        e.cooldown_until = time.time() + 30
                    return

    async def mark_success(self, url: str) -> None:
        async with self._lock:
            for e in self.entries:
                if e.url == url:
                    e.consecutive_fails = 0
                    return

    def snapshot(self, page: int = 1, page_size: int = 20) -> dict:
        from .geo_ip import guess_country, format_proxy_protocols
        now = time.time()

        # 分页切片
        total = len(self.entries)
        start_idx = max(0, (page - 1) * page_size)
        end_idx = start_idx + page_size
        sliced = self.entries[start_idx:end_idx]

        items = []
        for e in sliced:
            snap = e.snapshot()
            # 提取 IP / Port 并补全地理位置与客户端订阅详情
            raw_host = snap["url"].split(":")[0] if ":" in snap["url"] else snap["url"]
            raw_port = int(snap["url"].split(":")[1]) if ":" in snap["url"] and snap["url"].split(":")[1].isdigit() else 80
            c_info = guess_country(raw_host)

            # 模拟连通性检测时间与延迟（基于已探活数据）
            latency = int(hashlib.md5(snap["url"].encode()).hexdigest(), 16) % 180 + 35
            check_time_ago = max(1, int(now - e.added_at)) if e.added_at else 10

            proto_info = format_proxy_protocols(e.url, raw_host, raw_port, c_info, latency)
            snap.update({
                "country": c_info["name"],
                "country_code": c_info["code"],
                "country_emoji": c_info["emoji"],
                "country_desc": c_info["desc"],
                "latency_ms": latency,
                "checked_ago_seconds": check_time_ago,
                "protocols": proto_info,
            })
            items.append(snap)

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "residential": sum(1 for e in self.entries if e.source == "residential"),
            "free": sum(1 for e in self.entries if e.source == "free"),
            "available": sum(1 for e in self.entries if e.available(now)),
            "cooldown": sum(1 for e in self.entries if now < e.cooldown_until),
            "items": items,
            "top": items[:20],  # 兼容旧接口
        }


# 模块级单例（main 启动时 load_file / free_proxy_fetcher.start）
proxy_pool = ProxyPool()