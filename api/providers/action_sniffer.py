"""Next.js Server Action ID 动态嗅探器（Action Sniffer / ISSUE-03）。

背景：
Next.js Server Action 的 actionId 是编译期哈希，上游每次改版/构建都可能变化。
代码内静态硬编码的 `Next-Action: <hash>` 因此必然过期（实测 2026-08 claim 实际
ID 为 7fb1e44a…，与旧静态 7fa3d4d2… 已不同），造成生成/签到链路 404 / Action 不匹配。

方案：
- ActionSniffer 嗅探上游首页 HTML + 相关 JS bundle，正规化提取最新 Action ID。
- 双级缓存：内存 dict + JSON 文件持久化（原子写）；嗅探失败回退静态兜底值。
- get_action_id(kind) / refresh() / record_failure(kind) 供 Provider 与 registerer 接入；
  失配时 force_refresh=True 立即重新嗅探并自愈重试当前任务。
- 后台 keepalive：周期性嗅探，提前发现上游改版（自愈检测）。restart 后从持久化文件
  立即恢复，无需等首次嗅探。

嗅探来源（nanobanana-pro.com）：
- 首页 HTML 内的 <script src> 与 RSC flight 载荷列出全部 JS chunk URL。
- Action 定义在 chunk 中，minified 形态：
  `createServerReference)("<action_id>",...,a.callServer,void 0,a.findSourceMapURL,"<actionName>")`
  如 unifiedGenerateImageAction / unifiedEditImageAction / claimDailyCheckinAction。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from urllib.parse import urljoin, urlsplit

import httpx

from .. import config

log = logging.getLogger("action_sniffer")

DEFAULT_BASE = "https://nanobanana-pro.com"

# kind → 静态兜底 Action ID（嗅探失败/未启动时回退；站点改版后由嗅探自动更新）
STATIC_ACTION_IDS: dict[str, str] = {
    "generate": "7fb61a58991c7ab2bd6f0caa88d76a8194a714d6e3",
    "edit": "7f89ceae4364ecc4c8405d5cdb0aaa7da0ba5a87d0",
    "claim_daily_checkin": "7fa3d4d28767dbc090ad4228dff062a1e20d421ce2",
}

# 嗅探时每个 kind 对应的上游 Action 名候选（按优先级排列；对应 form/action 签名）
KIND_MARKERS: dict[str, list[str]] = {
    "generate": ["unifiedGenerateImageAction", "generateImageAction", "unifiedGenerateAction"],
    "edit": ["unifiedEditImageAction", "editImageAction", "editAction"],
    "claim_daily_checkin": ["claimDailyCheckinAction", "dailyCheckinAction"],
}

# 连续失败阈值 → 触发后台嗅探
_SNIFF_THRESHOLD = 3
# 后台嗅探最小间隔（秒），防打爆上游
_SNIFF_COOLDOWN = 300.0
# 单次嗅探最多的 JS chunk 数与并发数
_MAX_CHUNKS = 60
_CHUNK_CONCURRENCY = 6

# stale 响应识别标记（HTTP 404 之外，200 响应体内含这些字样也算 Action 失配）
_STALE_MARKERS = (
    "action not found",
    "failed to find server action",
    "invalid action",
    "unknown server action",
    "no server action",
)

# createServerReference)("<hex>",[^)]*,"<actionName>") —— 逆向确认的 Next.js 编码
_CSR_RE = re.compile(r'createServerReference\)\s*\(\s*"([0-9a-f]{20,80})"[^)]*?"([A-Za-z_][A-Za-z0-9_]*)"\s*\)')
_HEX_LIKE_RE = re.compile(r'[0-9a-f]{24,80}')


def _default_persist_path() -> str:
    """默认持久化路径：data/action_ids.json（可用 IF_ACTION_SNIFFER_FILE 覆盖）。"""
    return os.environ.get(
        "IF_ACTION_SNIFFER_FILE",
        os.path.join(os.path.dirname(config.DB_FILE) or "data", "action_ids.json"),
    )


def _keepalive_interval() -> int:
    return int(os.environ.get("IF_ACTION_SNIFFER_INTERVAL", "21600"))  # 默认 6h


def extract_server_actions(text: str) -> dict[str, str]:
    """从 HTML/JS 文本中提取 actionName → actionId（基于 createServerReference 签名）。"""
    out: dict[str, str] = {}
    for m in _CSR_RE.finditer(text):
        out.setdefault(m.group(2), m.group(1))
    return out


def _looks_like_action_id(h: str) -> bool:
    """近似判断：Next.js actionId 以 7f 开头（on-site 实测）或长度 >= 40。"""
    return len(h) >= 24 and (h[:2] == "7f" or len(h) >= 40)


def _nearby_action_id(text: str, name: str, window: int = 300) -> str | None:
    """降级策略：在 name 前方窗口内找最接近的形似 actionId 的 hex（csr 正则失配时兜底）。"""
    for m in re.finditer(re.escape(name), text):
        s = max(0, m.start() - window)
        region = text[s:m.end()]
        cands = [hm.group() for hm in _HEX_LIKE_RE.finditer(region)]
        for h in reversed(cands):  # 越靠近 name 越可能正确
            if _looks_like_action_id(h):
                return h
    return None


def extract_js_urls(html: str, base_url: str) -> list[str]:
    """从首页 HTML 提取 JS chunk URL（<script src> + flight/RSC 内嵌路径，去重后转绝对 URL）。

    S2 加固：仅保留与 base_url 同源的 URL，跨域脚本（CDN/统计）一律忽略，
    避免嗅探器以服务器身份抓取任意第三方地址。
    """
    seen: list[str] = []
    raw = html.replace("\\/", "/")  # flight 内 \/ 转义还原
    for m in re.finditer(r'"/?(_next/static/chunks/[A-Za-z0-9_./-]+\.js)"', raw):
        p = "/" + m.group(1).lstrip("/")
        if p not in seen:
            seen.append(p)
    for m in re.finditer(r'<script[^>]+src="([^"]+)"', html):
        src = m.group(1).strip()
        if src.endswith(".js") and src not in seen:
            seen.append(src)
    base_host = urlsplit(base_url).netloc
    out: list[str] = []
    for p in seen:
        abs_url = urljoin(base_url, p)
        if urlsplit(abs_url).netloc == base_host:  # 同源校验
            out.append(abs_url)
    return out


def is_stale_action_response(r: httpx.Response, text: str | None = None) -> bool:
    """判定响应是否因 Action ID 失配导致（404 / 响应体内含 action 失效标记）。"""
    if r.status_code == 404:
        return True
    if r.status_code != 200:
        return False
    body = (text if text is not None else (r.text or "")).lower()
    return any(marker in body for marker in _STALE_MARKERS)


class ActionSniffer:
    """动态嗅探 + 双级缓存（内存 / 文件持久化）的 Action ID 管理器。"""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        persist_path: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        proxy: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._base = (base_url or DEFAULT_BASE).rstrip("/")
        self._persist_path = persist_path or _default_persist_path()
        self._transport = transport
        self._proxy = proxy if proxy is not None else config.PROXY
        self._user_agent = user_agent or config.USER_AGENT
        self._tlock = threading.Lock()   # 保护内存缓存/计数器（同步快路径）
        self._alock: asyncio.Lock | None = None  # 串行嗅探（懒加载避免模块导入时绑定 loop）
        self._cache: dict[str, str] = {}  # kind -> 已嗅探/持久化的 Action ID（静态值只作兜底，不预置）
        self._failures: dict[str, int] = {k: 0 for k in STATIC_ACTION_IDS}
        self._last_sniff_at: float = 0.0
        self._sniffing = False
        self._client: httpx.AsyncClient | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._load_persisted()

    # ── 持久化 ──────────────────────────────────────
    def _load_persisted(self) -> None:
        try:
            if not os.path.exists(self._persist_path):
                return
            with open(self._persist_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    if k not in STATIC_ACTION_IDS:
                        continue
                    if isinstance(v, str) and v:
                        self._cache[k] = v
                    elif isinstance(v, dict) and isinstance(v.get("id"), str) and v["id"]:
                        self._cache[k] = v["id"]
        except (OSError, ValueError, json.JSONDecodeError) as e:
            log.warning("加载 Action 持久化缓存失败: %s", e)

    def _save_persisted(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._persist_path) or ".", exist_ok=True)
            tmp = self._persist_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._persist_path)
        except OSError as e:
            log.warning("保存 Action 持久化缓存失败: %s", e)

    # ── 公共接口 ────────────────────────────────────
    def peek(self, kind: str) -> str:
        """同步读取当前缓存（不触发网络）。"""
        with self._tlock:
            return self._cache.get(kind) or STATIC_ACTION_IDS.get(kind, "")

    def seed(self, kind: str, action_id: str) -> None:
        """预置/修正一个 Action ID（管理操作 / 测试用），并持久化。"""
        with self._tlock:
            self._cache[kind] = action_id
            self._failures.setdefault(kind, 0)
        self._save_persisted()

    async def get_action_id(self, kind: str, *, force_refresh: bool = False) -> str:
        """获取 Action ID。缓存命中直接返回；未命中/强制刷新则嗅探后返回，失败回退静态。"""
        if not force_refresh:
            with self._tlock:
                cached = self._cache.get(kind)
            if cached:
                return cached
        async with self._async_lock():
            if not force_refresh:
                with self._tlock:
                    cached = self._cache.get(kind)
                if cached:
                    return cached
            await self._do_sniff(specific_kind=kind)
            with self._tlock:
                return self._cache.get(kind) or STATIC_ACTION_IDS.get(kind, "")

    async def refresh(self, specific_kind: str | None = None) -> dict[str, str]:
        """主动嗅探刷新（保活 / 失配自愈 / 管理触发）。返回本次新解析到的 kind → id。"""
        async with self._async_lock():
            return await self._do_sniff(specific_kind=specific_kind)

    def record_failure(self, kind: str) -> str:
        """记录一次 Action 失配。连续失败达阈值且过冷却期后触发后台嗅探；返回当前可用 ID。"""
        with self._tlock:
            self._failures.setdefault(kind, 0)
            self._failures[kind] += 1
            count = self._failures[kind]
            cool_ok = (time.time() - self._last_sniff_at) > _SNIFF_COOLDOWN
            should_sniff = count >= _SNIFF_THRESHOLD and cool_ok and not self._sniffing
            if should_sniff:
                self._sniffing = True
                self._failures[kind] = 0
            current = self._cache.get(kind) or STATIC_ACTION_IDS.get(kind, "")
        if should_sniff:
            log.warning("ActionSniffer %s 连续失败 %d 次，触发后台嗅探", kind, count)
            self._spawn_background_refresh()
        return current

    def status(self) -> dict:
        """缓存的 Action ID 摘要（healthz / 看板用）。"""
        with self._tlock:
            return {
                "last_sniff_at": self._last_sniff_at,
                "cooldown": _SNIFF_COOLDOWN,
                "actions": {
                    k: (self._cache.get(k) or STATIC_ACTION_IDS.get(k, ""))[:12] + "…"
                    for k in STATIC_ACTION_IDS
                },
                "failures": dict(self._failures),
            }

    # ── 生命周期 / keepalive ────────────────────────
    def start_keepalive(self, interval_seconds: int | None = None) -> None:
        """启动后台周期嗅探（幂等）。interval 默认 IF_ACTION_SNIFFER_INTERVAL（6h）。"""
        if self._keepalive_task is not None and not self._keepalive_task.done():
            return
        interval = interval_seconds or _keepalive_interval()
        self._keepalive_task = asyncio.create_task(self._keepalive_loop(interval))

    def stop_keepalive(self) -> None:
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            self._keepalive_task = None

    async def aclose(self) -> None:
        self.stop_keepalive()
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _keepalive_loop(self, interval: int) -> None:
        try:
            while True:
                await asyncio.sleep(interval)
                with self._tlock:
                    stale = (time.time() - self._last_sniff_at) > interval
                if stale:
                    await self.refresh()
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001
            log.warning("Action 嗅探 keepalive 异常: %s", e)

    # ── 嗅探核心 ────────────────────────────────────
    def _async_lock(self) -> asyncio.Lock:
        if self._alock is None:
            self._alock = asyncio.Lock()
        return self._alock

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            kwargs: dict = dict(
                timeout=httpx.Timeout(30.0),
                headers={"User-Agent": self._user_agent},
                follow_redirects=False,  # S2 加固：不跟随重定向，防嗅探被导到任意主机
            )
            if self._transport is not None:
                kwargs["transport"] = self._transport
            else:
                # 空串代理会被 httpx 拒绝（Unknown scheme for proxy URL），归一化为 None 直连
                proxy = self._proxy
                if isinstance(proxy, str) and not proxy.strip():
                    proxy = None
                if proxy is not None:
                    kwargs["proxy"] = proxy
            self._client = httpx.AsyncClient(**kwargs)
        return self._client

    async def _do_sniff(self, specific_kind: str | None) -> dict[str, str]:
        client = self._ensure_client()
        results: dict[str, str] = {}
        try:
            html = await self._fetch_page(client)
            results.update(self._parse_text(html))
            chunk_urls = extract_js_urls(html, self._base)
            results.update(await self._scan_chunks(client, chunk_urls))

            with self._tlock:
                updated = {}
                for kind, aid in results.items():
                    if aid and kind in STATIC_ACTION_IDS and aid != self._cache.get(kind):
                        self._cache[kind] = aid
                        updated[kind] = aid
                self._last_sniff_at = time.time()
                self._sniffing = False
            if updated:
                self._save_persisted()
                log.info("ActionSniffer 嗅探刷新: %s", {k: v[:12] for k, v in updated.items()})
            return dict(results)
        except Exception as e:  # noqa: BLE001
            with self._tlock:
                self._sniffing = False
            log.warning("Action 嗅探异常: %s", e)
            return {}

    async def _fetch_page(self, client: httpx.AsyncClient) -> str:
        """抓取上游页面：优先 /zh（Provider 实际提交路径），失败回退 /。"""
        last_err: Exception | None = None
        for path in ("/zh", "/"):
            try:
                r = await client.get(f"{self._base}{path}")
                if r.status_code == 200:
                    return r.text
            except Exception as e:  # noqa: BLE001
                last_err = e
        if last_err is not None:
            log.warning("Action 嗅探首页失败(%s): %s", self._base, last_err)
        return ""

    def _parse_text(self, text: str) -> dict[str, str]:
        """从任意文本（HTML/JS）解析 kind → Action ID。"""
        if not text:
            return {}
        named = extract_server_actions(text)
        out: dict[str, str] = {}
        for kind, markers in KIND_MARKERS.items():
            matched = None
            for marker in markers:
                if marker in named:
                    matched = named[marker]
                    break
            if matched is None:
                for marker in markers:
                    if marker in text:
                        matched = _nearby_action_id(text, marker)
                        if matched:
                            break
            if matched:
                out[kind] = matched
        return out

    async def _scan_chunks(self, client: httpx.AsyncClient, chunk_urls: list[str]) -> dict[str, str]:
        sem = asyncio.Semaphore(_CHUNK_CONCURRENCY)
        found: dict[str, str] = {}

        async def grab(url: str) -> None:
            try:
                async with sem:
                    r = await client.get(url)
                if r.status_code != 200 or "createServerReference" not in r.text:
                    return
                parsed = self._parse_text(r.text)
                for k, v in parsed.items():
                    found.setdefault(k, v)
            except Exception:  # noqa: BLE001
                return

        await asyncio.gather(*(grab(u) for u in chunk_urls[:_MAX_CHUNKS]), return_exceptions=True)
        return found

    def _spawn_background_refresh(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 无运行事件循环（同步上下文）→ 独立事件循环同步等完
            try:
                asyncio.run(self.refresh())
            except Exception as e:  # noqa: BLE001
                log.warning("同步后台嗅探失败: %s", e)
            return
        loop.create_task(self._background_refresh())

    async def _background_refresh(self) -> None:
        try:
            await self.refresh()
        except Exception as e:  # noqa: BLE001
            log.warning("后台嗅探失败: %s", e)


# 全局单例（默认指向 nanobanana-pro.com + data/action_ids.json）
action_sniffer = ActionSniffer()