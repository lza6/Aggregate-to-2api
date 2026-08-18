"""minimaxh3.ai 提供商适配：authjs cookie 会话 + 号池（积分制）。

契约（逆向确认）：
- 认证：`__Secure-authjs.session-token` cookie（Auth.js JWE），业务请求带
  content-type/origin/referer 即可，不校验 CSRF。
- 生成：POST /api/v2/generate-image（txt2img/img2img）或 /generate-video（txt2vid），
  body {jobType, params:{modelId,prompt,aspectRatio,resolution,...}, assets?} →
  {code:0,data:{generationId,creditsUsed}}。
- 轮询：GET /api/v2/check-status?generationId=...&mode=polling → {status:completed,assets:[{imageUrl/videoUrl}]}。
- 积分：GET /api/get-user-credits → {data:{credits}}。新号赠 4 积分，用完即弃 → 号池自动补号。
- 注册：send-verification（需 turnstile captchaToken）→ 邮箱收 6 位码 → authjs callback/email-code。
- img2img 输入：assets.inputImages（直链/上传接口未确认，需实测）。
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time

import httpx

from .. import config
from .. import turnstile_client
from .base import (CAP_IMG2IMG, CAP_IMG2VID, CAP_TXT2IMG, CAP_TXT2VID, GenerationResult,
                   MOCK_REGISTER, ModelSpec, Provider, ProviderError, ProviderRateLimited)

log = logging.getLogger("providers.minimaxh3")

DEFAULT_BASE = "https://minimaxh3.ai"

# 上游模型清单（ID → (显示名, 能力, 积分费率, 分辨率)）
# 仅保留抓包定价表确认的模型，去掉高积分无实用模型
_UPSTREAM_MODELS = {
    "nano-banana-pro": ("Nano Banana Pro", (CAP_TXT2IMG, CAP_IMG2IMG), 4, ("1K", "2K", "4K")),
    "nano-banana-2": ("Nano Banana 2", (CAP_TXT2IMG,), 4, ("1K", "2K", "4K")),
    "nano-banana": ("Nano Banana", (CAP_TXT2IMG,), 2, ("1K",)),
    "gpt-image-2": ("GPT Image 2", (CAP_TXT2IMG,), 3, ("1K", "2K", "4K")),
    "seedream-5-lite": ("Seedream 5 Lite", (CAP_TXT2IMG,), 4, ("1K",)),
    "seedream-4.5": ("Seedream 4.5", (CAP_TXT2IMG,), 4, ("1K",)),
    "seedream-v4": ("Seedream V4", (CAP_TXT2IMG,), 3, ("1K",)),
    "seedance-1.5-pro": ("Seedance 1.5 Pro", (CAP_TXT2VID, CAP_IMG2VID), 4, ("480p", "720p")),
}

_ASPECTS = ("1:1", "3:4", "4:3", "9:16", "16:9", "21:9")
_VIDEO_DURATIONS = (4, 8, 12, 15)


class Minimaxh3Provider(Provider):
    prefix = "minimaxh3"
    display_name = "MiniMax H3"
    base_url = DEFAULT_BASE
    models: dict[str, ModelSpec] = {}

    def __init__(self) -> None:
        super().__init__()
        self.accounts: list[dict] = []       # 号池：{cookie, email, credits, ...}
        self._acc_idx = 0
        self._client: httpx.AsyncClient | None = None
        self._build_models()

    def _build_models(self) -> None:
        for upstream, (name, caps, credits, res) in _UPSTREAM_MODELS.items():
            is_video = CAP_TXT2VID in caps
            self.models[f"minimaxh3/{upstream}"] = ModelSpec(
                id=f"minimaxh3/{upstream}", provider=self.prefix, upstream_model=upstream,
                capabilities=caps, display_name=name,
                description=f"积分费率 {credits} 起",
                aspect_ratios=_ASPECTS, resolutions=res,
                credits=credits, account_required=True,
                meta={"video_durations": list(_VIDEO_DURATIONS)} if is_video else {},
            )

    # ── 生命周期 ──────────────────────────────────
    async def startup(self) -> None:
        self._client = httpx.AsyncClient(
            proxy=config.PROXY, timeout=httpx.Timeout(60.0),
            headers={"User-Agent": config.USER_AGENT, "Origin": self.base_url,
                     "Referer": f"{self.base_url}/zh"},
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        )
        # 号池账号动态拉取（实时，勿存启动快照——自动补号会持续新增）
        self.accounts = self._load_accounts()
        log.info("minimaxh3 号池加载 %d 账号", len(self.accounts))

    def _load_accounts(self) -> list[dict]:
        from ..account_pool import account_pool
        accs = account_pool.get("minimaxh3")
        # M1(审计修复): 生产进程过滤 mock 残留账号（cookie=mock-session），防测试号泄漏上线
        if not MOCK_REGISTER:
            accs = [a for a in accs if a.get("cookie") != "mock-session" and "mock" not in (a.get("note") or "")]
        return accs

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def needs_account(self) -> bool:
        return True

    # ── 号池取号 ──────────────────────────────────
    def _next_account(self) -> dict:
        """实时拉号池取一个有额度可用的账号；无账号返回 {}。"""
        self.accounts = self._load_accounts()
        if not self.accounts:
            return {}
        for _ in range(len(self.accounts)):
            acc = self.accounts[self._acc_idx % len(self.accounts)]
            self._acc_idx += 1
            if acc.get("credits", 0) > 0 and acc.get("cookie"):
                return acc
        # 全部额度耗尽 → 取第一个（上层会报额度不足）
        return self.accounts[self._acc_idx % len(self.accounts)]

    async def credits(self) -> int | None:
        return self._load_accounts_total()

    def _load_accounts_total(self) -> int:
        from ..account_pool import account_pool
        return account_pool.total_credits("minimaxh3")

    async def refresh_credits(self) -> None:
        """全号池刷新余额（号池管理器定时调用）。"""
        if not self._client:
            return
        from ..account_pool import account_pool
        for acc in self._load_accounts():
            cookie = acc.get("cookie")
            if not cookie:
                continue
            try:
                r = await self._client.get(f"{self.base_url}/api/get-user-credits",
                                           headers={"Cookie": cookie})
                data = r.json().get("data") or {}
                credits = int(data.get("credits", 0) or 0)
                account_pool.update_credits("minimaxh3", acc["email"], credits)
                acc["credits"] = credits
            except Exception as e:
                log.warning("minimaxh3 刷新余额失败 %s: %s", acc.get("email", "?"), e)

    # ── 生成 ──────────────────────────────────────
    async def generate(self, model: str, prompt: str, aspect_ratio: str,
                       images: list[bytes] | None = None, resolution: str = "1K",
                       download: bool = False, **kw) -> GenerationResult:
        upstream = model.split("/", 1)[-1]
        spec = self.models.get(model)
        is_video = spec is not None and CAP_TXT2VID in spec.capabilities
        acc = self._next_account()
        if not acc.get("cookie"):
            return GenerationResult(status="error", error="minimaxh3 号池无可用账号（请先注册/补充账号）")
        if int(acc.get("credits", 0) or 0) <= 0:
            return GenerationResult(status="error", error="minimaxh3 号池余额耗尽（新号 4 积分，自动补号中）")
        cookie = acc["cookie"]
        if cookie == "mock-session":
            # mock 号池账号：直接返回模拟结果（E2E 确定性，不依赖 _client/上游）
            return GenerationResult(
                status="completed",
                asset_url="https://mock.example/videos/x.mp4" if is_video else "https://mock.example/images/x.png")
        if not self._client:
            return GenerationResult(status="error", error="minimaxh3 未启动")
        try:
            if is_video:
                generation_id = await self._submit_video(cookie, upstream, prompt, aspect_ratio, resolution, kw.get("duration", 4))
                asset_url = await self._poll(cookie, generation_id, resource="video", timeout=900)
            else:
                generation_id = await self._submit_image(cookie, upstream, prompt, aspect_ratio, resolution, images)
                asset_url = await self._poll(cookie, generation_id, resource="image", timeout=300)
        except ProviderRateLimited as e:
            # H3(审计修复): 号池额度不足 → 标记该账号耗尽（DB 同步，防补号循环被"耗尽但状态 ok"卡死）
            acc["credits"] = 0
            try:
                from ..account_pool import account_pool
                account_pool.update_credits("minimaxh3", acc["email"], 0)
                account_pool.mark("minimaxh3", acc["email"], "exhausted")
            except Exception:
                pass
            # IMP-18: 连续限流 → 降级追踪
            if self._registry_ref:
                self._registry_ref.record_failure(self.prefix)
                self._registry_ref.mark_exhausted(self.prefix, acc.get("email", "?"))
            return GenerationResult(status="error", error=str(e))
        except ProviderError as e:
            return GenerationResult(status="error", error=str(e))

        # 可选下载（M6 审计修复: 视频按 video/mp4，图片按 image/png，勿全标 image/png）
        if download and asset_url:
            try:
                raw = await self._client.get(asset_url, timeout=httpx.Timeout(60))
                raw.raise_for_status()
                return GenerationResult(status="completed", asset_url=asset_url,
                                        asset_bytes=raw.content,
                                        asset_mime="video/mp4" if is_video else "image/png")
            except Exception as e:
                log.warning("minimaxh3 下载失败（不影响 URL 交付）: %s", e)
        return GenerationResult(status="completed", asset_url=asset_url)

    async def _submit_image(self, cookie, upstream, prompt, aspect_ratio, resolution, images):
        params = {
            "modelId": upstream, "prompt": prompt, "aspectRatio": aspect_ratio,
            "resolution": resolution, "customSize": resolution,
            "outputFormat": "jpeg", "outputCount": 1,
            "visibility": "private", "copyProtection": False,
        }
        body: dict = {"jobType": "img2img" if images else "txt2img", "params": params}
        if images:
            # img2img 输入图：base64 data URI 直传（上游接口 assets.inputImages；若失败可尝试直链）
            body["assets"] = {"inputImages": [
                {"dataUrl": f"data:image/png;base64,{base64.b64encode(im).decode()}"} for im in images
            ]}
        r = await self._client.post(f"{self.base_url}/api/v2/generate-image",
                                    headers={"Cookie": cookie}, json=body)
        return await self._handle_submit(r, cookie)

    async def _submit_video(self, cookie, upstream, prompt, aspect_ratio, resolution, duration):
        body = {
            "jobType": "txt2vid",
            "params": {
                "modelId": upstream, "prompt": prompt, "duration": int(duration),
                "resolution": resolution, "motionRange": "auto", "generateAudio": False,
                "outputCount": 1, "visibility": "public", "copyProtection": False,
                "aspectRatio": aspect_ratio, "cameraFixed": False,
            },
        }
        r = await self._client.post(f"{self.base_url}/api/v2/generate-video",
                                    headers={"Cookie": cookie}, json=body)
        return await self._handle_submit(r, cookie)

    async def _handle_submit(self, r: httpx.Response, cookie) -> str:
        data = r.json()
        if r.status_code != 200 or data.get("code", 0) != 0:
            msg = (data.get("message") or data) if isinstance(data, dict) else data
            if "credit" in str(msg).lower() or "insufficient" in str(msg).lower():
                raise ProviderRateLimited(f"minimaxh3 号池额度不足: {str(msg)[:120]}")
            raise ProviderError(f"minimaxh3 提交失败: {str(msg)[:200]}")
        gid = (data.get("data") or {}).get("generationId")
        if not gid:
            raise ProviderError(f"minimaxh3 响应缺 generationId: {str(data)[:200]}")
        # 提交即扣积分（响应 creditsUsed）
        used = (data.get("data") or {}).get("creditsUsed")
        if used:
            acc = self._find_by_cookie(cookie)
            if acc:
                from ..account_pool import account_pool
                acc["credits"] = max(0, int(acc.get("credits", 0)) - int(used))
                account_pool.update_credits("minimaxh3", acc["email"], acc["credits"])
        return gid

    def _find_by_cookie(self, cookie) -> dict | None:
        for acc in self.accounts:
            if acc.get("cookie") == cookie:
                return acc
        return None

    async def _poll(self, cookie, generation_id, resource, timeout) -> str:
        deadline = time.monotonic() + timeout
        url_key = "imageUrl" if resource == "image" else "videoUrl"
        while time.monotonic() < deadline:
            r = await self._client.get(
                f"{self.base_url}/api/v2/check-status",
                params={"generationId": generation_id, "mode": "polling",
                        "t": int(time.time() * 1000)},
                headers={"Cookie": cookie})
            data = r.json()
            status = data.get("status")
            if status == "completed":
                assets = data.get("assets") or []
                for a in assets:
                    url = a.get(url_key)
                    if url:
                        return url
                raise ProviderError("minimaxh3 completed 但缺产物 URL")
            if status in ("error", "failed"):
                raise ProviderError(f"minimaxh3 生成失败: {str(data.get('message') or data)[:200]}")
            await asyncio.sleep(2.0)
        raise ProviderError("minimaxh3 生成超时")
