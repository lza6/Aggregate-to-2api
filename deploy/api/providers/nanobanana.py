"""nanobanana-pro.com 提供商适配：better-auth 会话 + 号池（每日签到续额，非用完即丢）。

契约（逆向确认）：
- 认证：`__Secure-better-auth.session_token` + `__Secure-better-auth.session_data` cookie（7 天有效）。
- 注册：POST /api/auth/sign-up/email {email,password,name,callbackURL}（需 x-turnstile-token）→
  邮箱收 verify-email 链接 → GET 该链接确认 → POST /api/auth/sign-in/email 登录拿 session cookie。
- 签到：GET /api/credits/daily-checkin/status → {data:{hasClaimedToday,todayReward,rewards,nextClaimAt}}；
  领取走 Server Action（Next-Action claimDailyCheckinAction）；奖励 7 天循环 [4,4,8,4,4,4,10]，
  按美区时区重置（北京 15:00），积分 2 天过期。
- 余额：GET /api/credits/balance → {success,credits}。
- 生成：Next.js Server Action —— POST / (当前页) 带 `Next-Action: <unifiedGenerateImageAction ID>`、
  `Content-Type: text/plain;charset=UTF-8`、RSC 编码 body；响应 0: 行 {success,taskId}；
  轮询 GET /api/tasks/{taskId} 至 success 取 resultUrls。图生图换 editImageAction + imageUrls。
- 亮点：号池每天签到续额，不是用完即丢 → 号池「每日自动签到」守护任务。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx

from .. import config
from .base import CAP_IMG2IMG, CAP_TXT2IMG, MOCK_REGISTER, GenerationResult, ModelSpec, Provider, ProviderError, ProviderRateLimited

log = logging.getLogger("providers.nanobanana")

DEFAULT_BASE = "https://nanobanana-pro.com"

# 逆向确认的 Server Action ID（站点改版需重新抓取；契约见 README）
ACTION_GENERATE_IMG = "7fb61a58991c7ab2bd6f0caa88d76a8194a714d6e3"
ACTION_EDIT_IMG = "7f89ceae4364ecc4c8405d5cdb0aaa7da0ba5a87d0"
# 每日签到领取 claimDailyCheckinAction；与生成/图生图 Action 统一管理，站点改版需重新抓取
ACTION_CLAIM_DAILY_CHECKIN = "7fa3d4d28767dbc090ad4228dff062a1e20d421ce2"

# 上游模型清单（ID → (显示名, 能力)）
_UPSTREAM_MODELS = {
    "nano-banana-pro": ("Nano Banana Pro", (CAP_TXT2IMG, CAP_IMG2IMG)),
    "nano-banana-2": ("Nano Banana 2", (CAP_TXT2IMG,)),
    "nano-banana-2-lite": ("Nano Banana 2 Lite", (CAP_TXT2IMG,)),
    "seedream-5.0-pro": ("Seedream 5.0 Pro", (CAP_TXT2IMG,)),
    "seedream-5.0-lite": ("Seedream 5.0 Lite", (CAP_TXT2IMG,)),
    "gpt-image-2": ("GPT Image 2", (CAP_TXT2IMG,)),
    "grok-imagine": ("Grok Imagine", (CAP_TXT2IMG,)),
    "z-image": ("Z Image", (CAP_TXT2IMG,)),
}


class NanobananaProvider(Provider):
    prefix = "nanobanana"
    display_name = "Nano Banana Pro（每日签到）"
    base_url = DEFAULT_BASE
    models: dict[str, ModelSpec] = {}

    def __init__(self) -> None:
        super().__init__()
        self.accounts: list[dict] = []
        self._acc_idx = 0
        self._client: httpx.AsyncClient | None = None
        self._build_models()

    def _build_models(self) -> None:
        for upstream, (name, caps) in _UPSTREAM_MODELS.items():
            self.models[f"nanobanana/{upstream}"] = ModelSpec(
                id=f"nanobanana/{upstream}", provider=self.prefix, upstream_model=upstream,
                capabilities=caps, display_name=name,
                description="号池每日签到续额，非用完即丢",
                aspect_ratios=("1:1", "3:4", "4:3", "9:16", "16:9", "21:9"),
                resolutions=("1K", "2K", "4K"), credits=4, account_required=True,
            )

    def needs_account(self) -> bool:
        return True

    async def startup(self) -> None:
        self._client = httpx.AsyncClient(proxy=config.PROXY, timeout=httpx.Timeout(60.0),
                                         headers={"User-Agent": config.USER_AGENT})
        self.accounts = self._load_accounts()
        log.info("nanobanana 号池加载 %d 账号", len(self.accounts))

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _load_accounts(self) -> list[dict]:
        from ..account_pool import account_pool
        accs = account_pool.get("nanobanana")
        # M1(审计修复): 生产进程过滤 mock 残留账号，防测试号泄漏上线
        if not MOCK_REGISTER:
            accs = [a for a in accs if a.get("cookie") != "mock-session" and "mock" not in (a.get("note") or "")]
        return accs

    def _next_account(self) -> dict:
        self.accounts = self._load_accounts()
        if not self.accounts:
            return {}
        for _ in range(len(self.accounts)):
            acc = self.accounts[self._acc_idx % len(self.accounts)]
            self._acc_idx += 1
            if acc.get("credits", 0) > 0 and acc.get("cookie"):
                return acc
        return self.accounts[self._acc_idx % len(self.accounts)]

    async def credits(self) -> int | None:
        from ..account_pool import account_pool
        return account_pool.total_credits("nanobanana")

    # ── 生成（Next.js Server Action）───────────────
    def _rsc_encode(self, obj: dict) -> str:
        """RSC 编码 JSON：'$' 开头的字符串需转义为 '$$'（逆向确认）。"""
        s = json.dumps(obj, ensure_ascii=False)
        return s.replace("$", "$$") if "$" in s else s

    async def generate(self, model: str, prompt: str, aspect_ratio: str,
                       images: list[bytes] | None = None, resolution: str = "1K",
                       download: bool = False, **kw) -> GenerationResult:
        if not self._client:
            return GenerationResult(status="error", error="nanobanana 未启动")
        acc = self._next_account()
        if not acc.get("cookie"):
            return GenerationResult(status="error", error="nanobanana 号池无可用账号（请先注册/补充账号）")
        if int(acc.get("credits", 0) or 0) <= 0:
            return GenerationResult(status="error", error="nanobanana 号池余额耗尽（每日签到续额中）")
        cookie = acc["cookie"]
        if cookie == "mock-session":
            return GenerationResult(status="completed", asset_url="https://mock.example/images/nb.png")
        upstream = model.split("/", 1)[-1]
        try:
            if images:
                task_id = await self._submit_edit(cookie, upstream, prompt, aspect_ratio, images)
            else:
                task_id = await self._submit_image(cookie, upstream, prompt, aspect_ratio, resolution)
            asset_url = await self._poll_task(cookie, task_id, timeout=300)
        except ProviderRateLimited as e:
            # IMP-18: 连续限流 → 降级追踪
            if self._registry_ref:
                self._registry_ref.record_failure(self.prefix)
                self._registry_ref.mark_exhausted(self.prefix, acc.get("email", "?"))
            return GenerationResult(status="error", error=str(e))
        except ProviderError as e:
            return GenerationResult(status="error", error=str(e))
        except Exception as e:
            return GenerationResult(status="error", error=f"nanobanana 生成失败: {str(e)[:120]}")
        return GenerationResult(status="completed", asset_url=asset_url)

    def _action_headers(self, cookie: str, action_id: str) -> dict:
        return {
            "Cookie": cookie, "Next-Action": action_id,
            "Accept": "text/x-component",
            "Content-Type": "text/plain;charset=UTF-8",
            "Next-Router-State-Tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22zh%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%5D%2Cnull%2Cnull%2Ctrue",
        }

    async def _submit_image(self, cookie, upstream, prompt, aspect_ratio, resolution) -> str:
        body = [{"prompt": prompt, "model": upstream, "aspectRatio": aspect_ratio,
                 "resolution": resolution, "outputFormat": "png",
                 "googleSearch": False, "grokQualityMode": "fast"}]
        r = await self._client.post(f"{self.base_url}/zh",
                                    headers=self._action_headers(cookie, ACTION_GENERATE_IMG),
                                    content=self._rsc_encode(body))
        return await self._parse_action_response(r)

    async def _submit_edit(self, cookie, upstream, prompt, aspect_ratio, images) -> str:
        import base64
        # 图生图：先上传（multipart file + model）→ 拿 /api/assets/{id}/preview → 作为 imageUrls
        up = await self._client.post(
            f"{self.base_url}/api/upload/nano-banana",
            headers={"Cookie": cookie, "User-Agent": config.USER_AGENT},
            files={"file": ("edit.png", images[0], "image/png")},
            data={"model": upstream})
        if up.status_code != 200:
            raise ProviderError(f"nanobanana 上传失败: {up.status_code} {up.text[:120]}")
        url = (up.json() or {}).get("url")
        if not url:
            raise ProviderError(f"nanobanana 上传响应缺 url: {up.text[:120]}")
        body = [{"prompt": prompt, "model": upstream, "imageUrls": [url],
                 "aspectRatio": aspect_ratio, "resolution": "1K", "outputFormat": "png",
                 "googleSearch": False, "grokQualityMode": "fast"}]
        r = await self._client.post(f"{self.base_url}/zh",
                                    headers=self._action_headers(cookie, ACTION_EDIT_IMG),
                                    content=self._rsc_encode(body))
        return await self._parse_action_response(r)

    async def _parse_action_response(self, r: httpx.Response) -> str:
        if r.status_code != 200:
            raise ProviderError(f"nanobanana action 失败: HTTP {r.status_code}")
        # text/x-component 流：'0:' 行即返回值。
        # L4(审计修复): 遇无 success/taskId 的合法负载跳过（RSC 流可能多 0: 行），勿一遇就抛错
        text = r.text
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("0:"):
                continue
            payload = line[2:].strip()
            data = None
            try:
                data = json.loads(payload)
            except Exception:
                try:
                    data = json.loads(payload.replace("$$", "$"))  # RSC 转义回退
                except Exception:
                    continue
            if not isinstance(data, dict):
                continue
            if data.get("success"):
                task_id = data.get("taskId")
                if task_id:
                    return task_id
                continue
            if data.get("error") or "required" in str(data).lower():
                raise ProviderError(f"nanobanana 提交失败: {str(data)[:150]}")
            # 其它负载（无 success 字段）→ 跳过继续找
        raise ProviderError(f"nanobanana action 响应无有效 0: 行: {r.text[:150]}")

    async def _poll_task(self, cookie, task_id, timeout) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            r = await self._client.get(f"{self.base_url}/api/tasks/{task_id}",
                                       headers={"Cookie": cookie})
            data = r.json()
            state = data.get("state")
            if state == "success":
                urls = data.get("resultUrls") or []
                assets = data.get("assets") or []
                if urls:
                    return urls[0]
                for a in assets:
                    if a.get("downloadUrl"):
                        return a["downloadUrl"]
                    if a.get("previewUrl"):
                        return a["previewUrl"]
                raise ProviderError(f"nanobanana success 但缺 URL: {str(data)[:200]}")
            if state == "fail":
                raise ProviderError(f"nanobanana 生成失败: {str(data)[:200]}")
            await asyncio.sleep(3.0)
        raise ProviderError("nanobanana 生成超时")

