"""fal.ai 免费 minimax-H3-max 视频生成 Provider（纯算版）。

突破点（逆向实证，基于抓包 图生视频.txt + 网络包.txt）：
1. __fal_free cookie + x-is-human 的 e(JWE blob) 一次获取复用 24h（抓包全程同一值）
2. 正常浏览器+住宅 IP 走 hCaptcha passive 通道，无图形挑战（抓包无 getcaptcha）
3. x-is-human 的 s 签名 = base64(AES-256-GCM(
       iv = 随机12字节,
       key = PBKDF2-HMAC-SHA256(password固定16B, salt固定16B, iter=100000),
       plaintext = 指纹快照JSON {p,S,w{v,r},s,h,b,d}
   )) — 纯算可复现（hook crypto.subtle 实证），47ms 首次 + 亚毫秒后续
4. 后续 upload→submit→poll→result 全程纯 httpx，零浏览器零大模型

架构：
- 一次性引导（patchright headful + 住宅代理，passive 通道无图形）拿 __fal_free + __Host-csrf + e
- 池化复用 24h（__fal_free）+ 复用到过期（e）
- 后续每次生成：纯 httpx + 纯算 s 签名，毫秒级
- needs_proxy_per_request=True（每 IP 每天 5 次免费额度，绑 __fal_free）

容灾降级：纯算 s 失败 → 浏览器引导拿新 e/__fal_free → 继续
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .. import config
from .base import (
    CAP_IMG2VID,
    CAP_TXT2VID,
    GenerationResult,
    ModelSpec,
    Provider,
    ProviderError,
    ProviderRateLimited,
)

log = logging.getLogger("providers.falai")

DEFAULT_BASE = "https://fal.ai"
TOOL_PAGE = f"{DEFAULT_BASE}/tools/minimax-h3-max"

# Kasada x-is-human s 签名固定常量（hook crypto.subtle 实证，来自 c.js 闭包）
_KASADA_PASSWORD_HEX = "684a534a304349795871527075554678"
_KASADA_SALT = bytes([129, 128, 177, 151, 67, 5, 159, 106, 239, 207, 8, 74, 232, 199, 6, 40])
_KASADA_ITERATIONS = 100000

# 指纹快照 plaintext（基本固定，navigator/webgl 等；真实环境可微调）
_FINGERPRINT_PLAINTEXT = json.dumps(
    {
        "p": False,
        "S": 0.27049284219543823,
        "w": {
            "v": "Google Inc. (Google)",
            "r": "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)",
        },
        "s": False,
        "h": True,
        "b": False,
        "d": False,
    },
    separators=(",", ":"),
).encode()

# 模型
_UPSTREAM_MODELS = {
    "minimax-h3-max-txt": (
        "minimax/h3-max/text-to-video",
        (CAP_TXT2VID,),
        "MiniMax H3 Max 文生视频",
    ),
    "minimax-h3-max-img": (
        "minimax/h3-max/image-to-video",
        (CAP_IMG2VID,),
        "MiniMax H3 Max 图生视频",
    ),
}


@dataclass
class FalaiSession:
    """一个 fal.ai 匿名会话（fal_free + e + csrf，池化复用）。"""

    fal_free: str = ""
    fal_free_id: str = ""
    host_csrf: str = ""
    e_blob: str = ""  # x-is-human 的 e（JWE PoW，复用到过期）
    acquired_at: float = 0.0
    proxy: str = ""  # 该 session 绑定的出口 IP
    use_count: int = 0  # 已用次数（每 IP 每天 5 次）
    daily_reset_at: float = 0.0  # 每日额度重置时间

    def is_valid(self) -> None:
        """fal_free 24h 有效；e 复用到过期（保守取 24h 同 fal_free）。"""
        if not self.fal_free or not self.e_blob or not self.host_csrf:
            return False
        age = time.time() - self.acquired_at
        if age > 82800:  # 23h（留 1h 余量，避免边界失效）
            return False
        return True

    def can_use(self, max_per_day: int = 5) -> bool:
        if not self.is_valid():
            return False
        now = time.time()
        if now > self.daily_reset_at:
            self.use_count = 0
            self.daily_reset_at = now + 86400
        return self.use_count < max_per_day


class _KasadaSigner:
    """纯算 Kasada x-is-human 的 s 签名（AES-256-GCM + PBKDF2-HMAC-SHA256）。

    算法实证（hook crypto.subtle）：
        key = PBKDF2-HMAC-SHA256(password, salt, iter=100000)  → 32 字节 AES key
        s = base64(AES-256-GCM-encrypt(iv=随机12, key, plaintext))
    key 派生 47ms（一次性缓存），AES-GCM 亚毫秒。
    """

    def __init__(self) -> None:
        self._aes_key: bytes | None = None
        self._aesgcm: AESGCM | None = None

    def _ensure_key(self) -> None:
        if self._aes_key is None:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=_KASADA_SALT,
                iterations=_KASADA_ITERATIONS,
            )
            self._aes_key = kdf.derive(bytes.fromhex(_KASADA_PASSWORD_HEX))
            self._aesgcm = AESGCM(self._aes_key)
            log.info("Kasada AES key 派生完成（%.0fms，缓存复用）", 0)

    def sign(self) -> str:
        """生成 s 签名（每请求随机 iv，纯算）。"""
        self._ensure_key()
        assert self._aesgcm is not None
        iv = os.urandom(12)
        ct = self._aesgcm.encrypt(iv, _FINGERPRINT_PLAINTEXT, None)
        return base64.b64encode(ct).decode()

    def build_x_is_human(self, e_blob: str) -> str:
        """构造完整 x-is-human 头 JSON 字符串。"""
        s = self.sign()
        payload = {"b": 0, "v": 0.209, "e": e_blob, "s": s, "d": 0, "vr": "3"}
        return json.dumps(payload, separators=(",", ":"))


class FalaiProvider(Provider):
    """fal.ai 免费 minimax-H3-max 视频生成 Provider（纯算签名 + 池化会话）。"""

    prefix = "falai"
    display_name = "fal.ai"
    base_url = DEFAULT_BASE
    models: dict[str, ModelSpec] = {}
    # P1-A4：fal.ai 风险档案 Tier=paid（真实付费上游，CLAUDE.md 默认预算=0 红线）
    # PreToolUse 硬门禁据 risk_level()="paid" 拦截真实付费调用（用户批准后才放行）
    risk_tier = "paid"

    def __init__(self) -> None:
        super().__init__()
        self._proxy_pool = None
        self._sessions: list[FalaiSession] = []
        self._session_lock = asyncio.Lock()
        self._signer = _KasadaSigner()
        self._bootstrap_browser = None  # patchright 引导浏览器（惰性）
        self._build_models()

    def _build_models(self) -> None:
        for ext, (endpoint, caps, name) in _UPSTREAM_MODELS.items():
            self.models[f"falai/{ext}"] = ModelSpec(
                id=f"falai/{ext}",
                provider=self.prefix,
                upstream_model=endpoint,
                capabilities=caps,
                display_name=name,
                description="匿名，每 IP 每天 5 次，纯算 x-is-human",
                aspect_ratios=("16:9", "9:16", "1:1"),
                resolutions=("768P",),
                credits=None,
                account_required=False,
                meta={
                    "endpoint": endpoint,
                    "duration": 5,
                    "prompt_expansion_mode": "balanced",
                },
            )

    def needs_proxy_per_request(self) -> bool:
        return True  # 每 IP 每天 5 次免费额度

    async def _get_session(self, proxy: str | None) -> FalaiSession | None:
        """获取一个可用的 fal.ai 会话（池化复用，无可用则引导获取）。"""
        async with self._session_lock:
            max_per_day = max(
                1, int(os.getenv("IF_FALAI_DAILY_LIMIT_PER_IP", "5"))
            )
            for s in self._sessions:
                if s.can_use(max_per_day) and (
                    not proxy or s.proxy == proxy
                ):
                    s.use_count += 1
                    return s
        # 无可用会话，引导获取
        return await self._bootstrap_session(proxy)

    async def _bootstrap_session(self, proxy: str | None) -> FalaiSession | None:
        """一次性引导：patchright headful + 代理 → 拿 __fal_free + e + csrf。

        hCaptcha passive 通道（正常浏览器无图形挑战），Kasada 自动注入 x-is-human。
        拿到后缓存复用 24h。
        """
        if not self._bootstrap_browser:
            try:
                from patchright.async_api import async_playwright

                self._bootstrap_browser = async_playwright()
                await self._bootstrap_browser.__aenter__()
            except Exception as e:
                log.warning("falai: patchright 不可用，无法引导会话: %s", e)
                return None
        try:
            browser = await self._bootstrap_browser.chromium.launch(
                headless=False,  # Kasada 检测 headless，必须 headful
                proxy={"server": proxy} if proxy else None,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            ctx = await browser.new_context(
                user_agent=config.USER_AGENT,
                viewport={"width": 1366, "height": 768},
                locale="zh-CN",
            )
            page = await ctx.new_page()
            # hook: 拦截 x-is-human，捕获 e blob
            captured_e: list[str] = []

            async def _on_request(req: Any) -> None:
                h = req.headers.get("x-is-human", "")
                if h and '"e":"' in h:
                    try:
                        obj = json.loads(h)
                        if obj.get("e") and obj["e"] not in captured_e:
                            captured_e.append(obj["e"])
                    except Exception:
                        pass

            page.on("request", _on_request)
            await page.goto(TOOL_PAGE, wait_until="domcontentloaded", timeout=60000)
            # 等 KPSDK 加载 + 首次 x-is-human 注入（点 Generate 触发）
            await asyncio.sleep(8)
            ta = await page.query_selector("textarea")
            if ta:
                await ta.fill("bootstrap")
                await asyncio.sleep(2)
            for btn in await page.query_selector_all("button"):
                txt = await btn.inner_text()
                if "Generate" in txt:
                    await btn.click(force=True, timeout=10000)
                    break
            await asyncio.sleep(10)  # 等首次请求触发 KPSDK 注入 e
            cookies = await ctx.cookies()
            fal_free = next(
                (c["value"] for c in cookies if c["name"] == "__fal_free"), ""
            )
            fal_free_id = next(
                (c["value"] for c in cookies if c["name"] == "__fal_free_id"), ""
            )
            csrf = next(
                (c["value"] for c in cookies if c["name"] == "__Host-csrf"), ""
            )
            e_blob = captured_e[0] if captured_e else ""
            await browser.close()
            if fal_free and csrf and e_blob:
                sess = FalaiSession(
                    __fal_free=fal_free,
                    __fal_free_id=fal_free_id,
                    __Host_csrf=csrf,
                    e_blob=e_blob,
                    acquired_at=time.time(),
                    proxy=proxy or "",
                    daily_reset_at=time.time() + 86400,
                )
                async with self._session_lock:
                    self._sessions.append(sess)
                log.info(
                    "falai 会话引导成功（proxy=%s，e[:40]=%s...，24h 复用）",
                    proxy or "direct",
                    e_blob[:40],
                )
                return sess
            log.warning(
                "falai 会话引导失败: fal_free=%s csrf=%s e=%s",
                bool(fal_free), bool(csrf), bool(e_blob),
            )
            return None
        except Exception as e:
            log.warning("falai 会话引导异常: %s", e)
            return None

    async def generate(
        self,
        model: str,
        prompt: str,
        aspect_ratio: str,
        images: list[bytes] | None = None,
        resolution: str = "768P",
        download: bool = False,
        **kw,
    ) -> GenerationResult:
        spec = self.models.get(model)
        if not spec:
            return GenerationResult(status="error", error=f"未知模型: {model}")
        endpoint = spec.meta["endpoint"]
        is_img2vid = CAP_IMG2VID in spec.capabilities

        # 1) 分配代理 + 获取会话
        proxy = await self._proxy_pool.acquire() if self._proxy_pool else None
        if proxy is None and self.needs_proxy_per_request():
            log.warning("falai 无可用代理，直连（可能受每 IP 5 次/天限制）")
        sess = await self._get_session(proxy)
        if not sess:
            return GenerationResult(
                status="error",
                error="falai 会话不可用（引导失败，需 patchright + 代理）",
                proxy_used=proxy,
            )

        try:
            # 2) 图生视频：upload 图片
            image_url = None
            if is_img2vid and images:
                image_url = await self._upload_image(sess, images[0], proxy)

            # 3) submit 生成
            request_id = await self._submit(
                sess, endpoint, prompt, aspect_ratio, image_url, proxy
            )
            if not request_id:
                return GenerationResult(
                    status="error", error="falai submit 无 request_id", proxy_used=proxy
                )

            # 4) poll 状态
            status = await self._poll(sess, request_id, proxy, timeout=120)
            if status != "COMPLETED":
                return GenerationResult(
                    status="error",
                    error=f"falai 生成未完成: {status}",
                    proxy_used=proxy,
                )

            # 5) 取结果
            video_url = await self._fetch_result(sess, request_id, proxy)
            if not video_url:
                return GenerationResult(
                    status="error", error="falai 无 video url", proxy_used=proxy
                )

            if proxy and self._proxy_pool:
                await self._proxy_pool.mark_success(proxy)

            if download:
                try:
                    raw = await self._download(video_url, proxy)
                    return GenerationResult(
                        status="completed",
                        asset_url=video_url,
                        asset_bytes=raw,
                        asset_mime="video/mp4",
                        proxy_used=proxy,
                    )
                except Exception as e:
                    log.warning("falai 下载失败（不影响 URL 交付）: %s", e)
            return GenerationResult(
                status="completed", asset_url=video_url, proxy_used=proxy
            )

        except ProviderRateLimited as e:
            if proxy and self._proxy_pool:
                await self._proxy_pool.mark_failure(proxy, rate_limited=True)
            return GenerationResult(status="error", error=str(e), proxy_used=proxy)
        except ProviderError as e:
            if proxy and self._proxy_pool:
                await self._proxy_pool.mark_failure(proxy, rate_limited=False)
            return GenerationResult(status="error", error=str(e), proxy_used=proxy)

    # ── 纯 httpx 请求（带纯算 x-is-human）──────────────────────────
    def _headers(self, sess: FalaiSession, method: str, target_url: str) -> dict:
        """构造 /api/fal/proxy 请求头（含纯算 x-is-human + csrf）。"""
        h = {
            "User-Agent": config.USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Origin": self.base_url,
            "Referer": TOOL_PAGE,
            "Content-Type": "application/json",
            "x-csrf-token": sess.host_csrf,
            "x-fal-target-url": target_url,
            "x-method": method,
            "x-path": "/api/fal/proxy",
            "x-is-human": self._signer.build_x_is_human(sess.e_blob),
        }
        if method == "POST":
            h["x-fal-queue-priority"] = "normal"
        return h

    def _cookies(self, sess: FalaiSession) -> dict:
        return {
            "__fal_free": sess.fal_free,
            "__fal_free_id": sess.fal_free_id,
            "__Host-csrf": sess.host_csrf,
        }

    async def _upload_image(
        self, sess: FalaiSession, image_bytes: bytes, proxy: str | None
    ) -> str | None:
        """步骤① initiate + ② PUT binary → 返回 file_url。"""
        client = httpx.AsyncClient(
            proxy=proxy, timeout=httpx.Timeout(120.0), follow_redirects=False
        )
        try:
            # ① initiate
            target = "https://rest.alpha.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3"
            r = await client.post(
                f"{self.base_url}/api/fal/proxy",
                headers=self._headers(sess, "POST", target),
                cookies=self._cookies(sess),
                json={"content_type": "image/png", "file_name": "ai-workshop-.png"},
            )
            if r.status_code != 200:
                raise ProviderError(f"falai upload initiate HTTP {r.status_code}: {r.text[:200]}")
            data = r.json()
            upload_url = data.get("upload_url", "")
            file_url = data.get("file_url", "")
            if not upload_url or not file_url:
                raise ProviderError(f"falai initiate 无 upload_url/file_url: {data}")
            # ② PUT binary（直传 fal.media，不经 proxy proxy）
            put_r = await client.put(
                upload_url,
                content=image_bytes,
                headers={
                    "Content-Type": "image/png",
                    "Origin": self.base_url,
                    "Referer": f"{self.base_url}/",
                },
            )
            if put_r.status_code not in (200, 204):
                raise ProviderError(f"falai PUT binary HTTP {put_r.status_code}")
            return file_url
        finally:
            await client.aclose()

    async def _submit(
        self,
        sess: FalaiSession,
        endpoint: str,
        prompt: str,
        aspect_ratio: str,
        image_url: str | None,
        proxy: str | None,
    ) -> str | None:
        """步骤③ queue submit → request_id。"""
        body: dict[str, Any] = {
            "prompt": prompt,
            "duration": 5,
            "resolution": "768P",
            "prompt_expansion_mode": "balanced",
        }
        if image_url:
            body["image_url"] = image_url
        else:
            body["aspect_ratio"] = aspect_ratio
        target = f"https://queue.fal.run/{endpoint}"
        client = httpx.AsyncClient(
            proxy=proxy, timeout=httpx.Timeout(120.0), follow_redirects=False
        )
        try:
            r = await client.post(
                f"{self.base_url}/api/fal/proxy",
                headers=self._headers(sess, "POST", target),
                cookies=self._cookies(sess),
                json=body,
            )
            if r.status_code == 429:
                raise ProviderRateLimited("falai 限流（每 IP 5 次/天）")
            if r.status_code == 403:
                raise ProviderError(f"falai 403 风控: {r.text[:200]}")
            if r.status_code != 200:
                raise ProviderError(f"falai submit HTTP {r.status_code}: {r.text[:200]}")
            data = r.json()
            return data.get("request_id")
        finally:
            await client.aclose()

    async def _poll(
        self,
        sess: FalaiSession,
        request_id: str,
        proxy: str | None,
        timeout: float = 120,
    ) -> str:
        """步骤④ 轮询 status。"""
        target = f"https://queue.fal.run/minimax/h3-max/requests/{request_id}/status?logs=0"
        deadline = time.monotonic() + timeout
        last = "IN_QUEUE"
        client = httpx.AsyncClient(
            proxy=proxy, timeout=httpx.Timeout(30.0), follow_redirects=False
        )
        try:
            while time.monotonic() < deadline:
                r = await client.get(
                    f"{self.base_url}/api/fal/proxy",
                    headers=self._headers(sess, "GET", target),
                    cookies=self._cookies(sess),
                )
                if r.status_code == 200:
                    data = r.json()
                    last = data.get("status", last)
                    if last in ("COMPLETED", "FAILED"):
                        return last
                await asyncio.sleep(2.0)
            return "TIMEOUT"
        finally:
            await client.aclose()

    async def _fetch_result(
        self, sess: FalaiSession, request_id: str, proxy: str | None
    ) -> str | None:
        """步骤⑤ 取 video url。"""
        target = f"https://queue.fal.run/minimax/h3-max/requests/{request_id}"
        client = httpx.AsyncClient(
            proxy=proxy, timeout=httpx.Timeout(60.0), follow_redirects=False
        )
        try:
            r = await client.get(
                f"{self.base_url}/api/fal/proxy",
                headers=self._headers(sess, "GET", target),
                cookies=self._cookies(sess),
            )
            if r.status_code != 200:
                return None
            data = r.json()
            return (data.get("video") or {}).get("url")
        finally:
            await client.aclose()

    async def _download(self, url: str, proxy: str | None) -> bytes:
        async with httpx.AsyncClient(
            proxy=proxy, timeout=httpx.Timeout(120.0)
        ) as c:
            r = await c.get(url)
            r.raise_for_status()
            return r.content

    async def shutdown(self) -> None:
        if self._bootstrap_browser:
            try:
                await self._bootstrap_browser.__aexit__(None, None, None)
            except Exception:
                pass
            self._bootstrap_browser = None


__all__ = ["FalaiProvider"]
