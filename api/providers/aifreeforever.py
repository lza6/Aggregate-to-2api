"""aifreeforever.com 提供商适配：匿名 + Turnstile 验证码 + 每次请求轮换出口 IP。

契约（逆向确认）：
- 完全匿名（无登录/API key）；唯一门槛是 Cloudflare Turnstile token（sitekey 见 config）。
- 自定义头：x-api-secret（空串）、x-captcha-verified-at（epoch ms）、x-turnstile-token（与 body 同值）。
- 文生图：POST /api/v2/generate-image body {modelId,prompt,aspect_ratio,turnstileToken} →
  {success:true,images:[url]}（同步返回，无轮询，15-30s）。
- 图生图：同端点 + referenceImageUrl（base64 data URI 或图床直链，最多 3 张）；
  前置 POST /api/moderate-image（multipart file → {result:pass}）。
- 风控：每 IP 每日限额，429 返回 {waitTime:秒} 且逐次递增，约 24h 重置 → 每请求必须轮换出口 IP。
- 求解 token 走 turnstile_client（cf_solver），token 与签发 IP 绑定 → 每 IP 需独立求解。
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time

import httpx

from .. import config
from .. import turnstile_client
from .base import CAP_IMG2IMG, CAP_TXT2IMG, GenerationResult, ModelSpec, Provider, ProviderError, ProviderRateLimited

log = logging.getLogger("providers.aifreeforever")

DEFAULT_BASE = "https://aifreeforever.com"
# 上游 Turnstile sitekey（逆向自前端构建；站点变更时改 config）
SITEKEY = "0x4AAAAAADGj2nznqyRfB0Lj"

# 上游模型清单（ID → (显示名, 能力, 支持比例)）
_UPSTREAM_MODELS = {
    "gpt-image-2": ("GPT Image 2", (CAP_TXT2IMG, CAP_IMG2IMG), ("1:1", "3:2", "2:3", "16:9", "9:16")),
    "flux-fast": ("FLUX Fast", (CAP_TXT2IMG,), None),
    "z-image-turbo": ("Z-Image Turbo", (CAP_TXT2IMG,), None),
    "p-image": ("P-Image", (CAP_TXT2IMG,), None),
    "hidream-l1-fast": ("HiDream L1 Fast", (CAP_TXT2IMG,), None),
    "flux-schnell": ("FLUX Schnell", (CAP_TXT2IMG,), None),
    "imagen-4": ("Imagen 4 Fast", (CAP_TXT2IMG,), None),
    "imagen-3": ("Imagen 3 Fast", (CAP_TXT2IMG,), None),
    "nano-banana": ("Nano Banana", (CAP_TXT2IMG,), None),
    "nano-banana-2": ("Nano Banana 2", (CAP_TXT2IMG,), None),
    "nano-banana-pro": ("Nano Banana Pro", (CAP_TXT2IMG,), None),
    "seedream-4-5": ("Seedream 4.5", (CAP_TXT2IMG,), None),
    "seedream-5": ("Seedream 5 Lite", (CAP_TXT2IMG,), None),
    "seedream-4": ("Seedream 4", (CAP_TXT2IMG, CAP_IMG2IMG), None),
    "flux-2-pro": ("FLUX 2 Pro", (CAP_TXT2IMG,), None),
    "flux-2-max": ("FLUX 2 Max", (CAP_TXT2IMG,), None),
    "grok-imagine": ("Grok Imagine", (CAP_TXT2IMG, CAP_IMG2IMG), None),
    "qwen-image": ("Qwen Image", (CAP_TXT2IMG, CAP_IMG2IMG), None),
    "ideogram-v3": ("Ideogram V3 Turbo", (CAP_TXT2IMG,), None),
}

_BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"),
    "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin",
}


class AifreeforeverProvider(Provider):
    prefix = "aifreeforever"
    display_name = "AIFreeForever"
    base_url = DEFAULT_BASE
    models: dict[str, ModelSpec] = {}

    def __init__(self) -> None:
        super().__init__()
        self._proxy_pool = None      # main 注入：每请求取一个新住宅 IP
        self._build_models()

    def _build_models(self) -> None:
        for upstream, (name, caps, ratios) in _UPSTREAM_MODELS.items():
            self.models[f"aifreeforever/{upstream}"] = ModelSpec(
                id=f"aifreeforever/{upstream}", provider=self.prefix, upstream_model=upstream,
                capabilities=caps, display_name=name,
                description="匿名使用，每 IP 每日限额",
                aspect_ratios=ratios or ("1:1", "3:4", "4:3", "16:9", "9:16", "3:2", "2:3"),
                resolutions=(), credits=None, account_required=False,
            )

    def needs_proxy_per_request(self) -> bool:
        return True  # 每请求必须新出口 IP（每 IP 每日限额）

    async def generate(self, model: str, prompt: str, aspect_ratio: str,
                       images: list[bytes] | None = None, resolution: str = "1K",
                       download: bool = False, **kw) -> GenerationResult:
        # 1) 分配出口 IP（优先代理池轮换，无代理时回退直连）
        proxy = None
        if self._proxy_pool is not None:
            proxy = await self._proxy_pool.acquire()
        if proxy is None:
            if self.needs_proxy_per_request():
                log.warning("aifreeforever 无可用代理，使用直连（可能受每 IP 每日限额限制）")
            # 无代理时回退直连，让请求继续（可能被上游限流，但不完全阻断）

        # 2) 该 IP 专属求解 Turnstile（token 与 IP 绑定）
        # 用 /image-generators 页面作为 turnstile 上下文（逆向确认该页面有 Turnstile 挂载）
        # 先直连求解（cf_solver 带 kookeey 代理 → Cloudflare 100% 拦截 aifreeforever turnstile）
        turnstile_page = f"{self.base_url}/image-generators"
        token = None
        for attempt_i in range(2):
            try:
                token, _ = await turnstile_client.solve_turnstile(
                    config.CF_SOLVER_URL, turnstile_page, SITEKEY,
                    config.TURNSTILE_TIMEOUT, proxy=None)  # 始终直连，代理绕 cf 会触发拦截
                break
            except Exception as e:
                log.warning("aifreeforever turnstile 求解失败(第%d次): %s", attempt_i + 1, e)
                if attempt_i == 0:
                    await asyncio.sleep(3)
        if token is None:
            return GenerationResult(status="error",
                error="aifreeforever 验证码求解失败（cf_solver 直连超时）",
                proxy_used=proxy)

        # 3) 图生图前置合规检查
        if images:
            try:
                ok = await self._moderate(images[0], proxy)
                if not ok:
                    return GenerationResult(status="error", error="aifreeforever 图片合规检查未通过", proxy_used=proxy)
            except Exception as e:
                return GenerationResult(status="error", error=f"aifreeforever 图片检查失败: {str(e)[:120]}", proxy_used=proxy)

        # 4) 生成（成功/失败回填代理池，驱动冷却与 24h 每日限额——M9 审计修复）
        try:
            urls = await self._generate(token, model.split("/", 1)[-1], prompt,
                                        aspect_ratio, images, proxy)
        except ProviderRateLimited as e:
            if proxy and self._proxy_pool is not None:
                await self._proxy_pool.mark_failure(proxy, rate_limited=True)
            return GenerationResult(status="error", error=str(e), proxy_used=proxy)
        except ProviderError as e:
            if proxy and self._proxy_pool is not None:
                await self._proxy_pool.mark_failure(proxy, rate_limited=False)
            return GenerationResult(status="error", error=str(e), proxy_used=proxy)
        if proxy and self._proxy_pool is not None:
            await self._proxy_pool.mark_success(proxy)

        url = urls[0] if urls else None
        if not url:
            return GenerationResult(status="error", error="aifreeforever 响应无图片 URL")
        if download:
            try:
                raw = await self._download(url, proxy)
                return GenerationResult(status="completed", asset_url=url,
                                        asset_bytes=raw, asset_mime="image/webp",
                                        proxy_used=proxy)
            except Exception as e:
                log.warning("aifreeforever 下载失败（不影响 URL 交付）: %s", e)
        return GenerationResult(status="completed", asset_url=url, proxy_used=proxy)

    # ── 内部调用 ──────────────────────────────────
    def _headers(self, token: str | None = None) -> dict:
        h = dict(_BROWSER_HEADERS)
        h.update({
            "Origin": self.base_url, "Referer": f"{self.base_url}/image-generators",
            "x-api-secret": "",
        })
        if token:
            h["x-captcha-verified-at"] = str(int(time.time() * 1000))
            h["x-turnstile-token"] = token
        return h

    async def _moderate(self, image_bytes: bytes, proxy: str | None) -> bool:
        async with httpx.AsyncClient(proxy=proxy, timeout=httpx.Timeout(60.0)) as c:
            r = await c.post(f"{self.base_url}/api/moderate-image",
                             headers=self._headers(),
                             files={"file": ("edit.png", image_bytes, "image/png")})
            return r.json().get("result") == "pass"

    async def _generate(self, token, upstream, prompt, aspect_ratio, images, proxy) -> list[str]:
        body: dict = {"modelId": upstream, "prompt": prompt,
                      "aspect_ratio": aspect_ratio, "turnstileToken": token}
        if images:
            # base64 data URI 直传（逆向实证可行）；最多 3 张
            refs = [f"data:image/png;base64,{base64.b64encode(im).decode()}" for im in images[:3]]
            if len(refs) == 1:
                body["referenceImageUrl"] = refs[0]
            else:
                body["referenceImageUrls"] = refs
        async with httpx.AsyncClient(proxy=proxy, timeout=httpx.Timeout(120.0)) as c:
            r = await c.post(f"{self.base_url}/api/v2/generate-image",
                             headers=self._headers(token), json=body)
            try:
                data = r.json()
            except Exception:
                raise ProviderError(f"aifreeforever 生成失败: HTTP {r.status_code} {r.text[:200]}")
            if r.status_code == 429:
                wait = data.get("waitTime") or 60
                raise ProviderRateLimited(f"aifreeforever 限流（IP 每日限额），等待 {wait}s")
            if r.status_code != 200 or not data.get("success"):
                raise ProviderError(f"aifreeforever 生成失败: {str(data)[:200]}")
            return data.get("images") or []

    async def _download(self, url, proxy) -> bytes:
        async with httpx.AsyncClient(proxy=proxy, timeout=httpx.Timeout(60.0)) as c:
            r = await c.get(url)
            r.raise_for_status()
            return r.content
