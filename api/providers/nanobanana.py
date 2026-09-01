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
from typing import Any

import httpx

from .. import config
from .action_sniffer import action_sniffer, is_stale_action_response
from .base import (
    CAP_IMG2IMG,
    CAP_TXT2IMG,
    MOCK_REGISTER,
    GenerationResult,
    ModelSpec,
    Provider,
    ProviderError,
    ProviderRateLimited,
)

log = logging.getLogger("providers.nanobanana")

DEFAULT_BASE = "https://nanobanana-pro.com"

# 逆向确认的 Server Action ID（站点改版需重新抓取；契约见 README）。
# 运行时经 ActionSniffer 动态解析（ISSUE-03），嗅探失败才回退到下列静态兜底值。
ACTION_GENERATE_IMG = "7fb61a58991c7ab2bd6f0caa88d76a8194a714d6e3"
ACTION_EDIT_IMG = "7f89ceae4364ecc4c8405d5cdb0aaa7da0ba5a87d0"
# 每日签到领取 claimDailyCheckinAction；与生成/图生图 Action 统一由 ActionSniffer 管理
ACTION_CLAIM_DAILY_CHECKIN = "7fa3d4d28767dbc090ad4228dff062a1e20d421ce2"

# 内部 Action kind → Sniffer 逻辑名（STATIC_ACTION_IDS 键）
_KIND_GENERATE = "generate"
_KIND_EDIT = "edit"
_KIND_CLAIM = "claim_daily_checkin"

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


# v6.5.1: 每张图消耗积分（逆向自上游 encodeImageCost，minified js 21561 模块）。
# 未命中回退 _DEFAULT_CREDITS_PER_IMAGE=4；档位值表内硬编码，无全局倍数。
_CREDITS_PER_IMAGE = {
    "nano-banana-pro": 4,
    "nano-banana-pro:4K": 14,
    "nano-banana-2:1K": 5,
    "nano-banana-2:2K": 8,
    "nano-banana-2:4K": 12,
    "nano-banana-2-lite:1K": 3,
    "gpt-image-2:1K": 6,
    "gpt-image-2:2K": 10,
    "gpt-image-2:4K": 14,
    "seedream-5.0-pro:1K": 7,
    "seedream-5.0-pro:2K": 14,
    "seedream-5.0-lite:2K": 6,
    "seedream-5.0-lite:3K": 6,
    "grok-imagine:fast": 5,
    "grok-imagine:quality": 6,
    "grok-imagine:edit": 5,
    "z-image": 2,
}
_DEFAULT_CREDITS_PER_IMAGE = 4


def image_credit_cost(
    upstream: str, resolution: str = "1K", task_type: str | None = None, quality_mode: str | None = None
) -> int:
    """按上游模型 + 分辨率返回单张图消耗的积分（镜像上游 encodeImageCost）。

    _CREDITS_PER_IMAGE 是唯一事实源：表内每个档位（含 `:1K/:2K/:4K`）都必须被本函数
    路由到，否则漏档回退默认 4 会少扣积分（P1-5）。分支的 res 集合须覆盖表内全部档位。
    """
    res = resolution or "1K"
    if upstream == "grok-imagine":
        key = (
            "grok-imagine:edit"
            if task_type == "edit"
            else "grok-imagine:quality"
            if quality_mode == "quality"
            else "grok-imagine:fast"
        )
        return _CREDITS_PER_IMAGE.get(key, _DEFAULT_CREDITS_PER_IMAGE)
    lookup = upstream
    if upstream == "nano-banana-pro" and res == "4K":
        lookup = "nano-banana-pro:4K"
    elif upstream == "nano-banana-2" and res in ("1K", "2K", "4K"):
        lookup = f"nano-banana-2:{res}"
    elif upstream == "nano-banana-2-lite":
        lookup = "nano-banana-2-lite:1K"
    elif upstream == "gpt-image-2" and res in ("1K", "2K", "4K"):
        lookup = f"gpt-image-2:{res}"
    elif upstream == "seedream-5.0-pro" and res in ("1K", "2K", "3K", "4K"):
        # 表仅细粒度定价 1K/2K；3K/4K 归并到 2K 档（2K=14）。
        lookup = "seedream-5.0-pro:1K" if res == "1K" else "seedream-5.0-pro:2K"
    elif upstream == "seedream-5.0-lite" and res in ("1K", "2K", "3K", "4K"):
        # 表仅含 2K/3K 档（均 6）；1K/4K 归并到 2K 档（lite 1K≈2K 成本，避免 1K 落默认 4 低估）。
        lookup = "seedream-5.0-lite:2K" if res in ("1K", "2K") else "seedream-5.0-lite:3K"
    elif upstream == "z-image":
        lookup = "z-image"
    return _CREDITS_PER_IMAGE.get(lookup, _DEFAULT_CREDITS_PER_IMAGE)


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
        # ActionSniffer 实例；None → 用模块级共享单例（测试可注入 Fake）
        self._action_sniffer: Any | None = None
        self._build_models()

    def _build_models(self) -> None:
        for upstream, (name, caps) in _UPSTREAM_MODELS.items():
            self.models[f"nanobanana/{upstream}"] = ModelSpec(
                id=f"nanobanana/{upstream}",
                provider=self.prefix,
                upstream_model=upstream,
                capabilities=caps,
                display_name=name,
                description="号池每日签到续额，非用完即丢",
                aspect_ratios=("1:1", "3:4", "4:3", "9:16", "16:9", "21:9"),
                resolutions=("1K", "2K", "4K"),
                credits=4,
                account_required=True,
            )

    def needs_account(self) -> bool:
        return True

    async def startup(self) -> None:
        self._client = httpx.AsyncClient(
            proxy=config.PROXY, timeout=httpx.Timeout(60.0), headers={"User-Agent": config.USER_AGENT}
        )
        self.accounts = await self._async_load_accounts()
        # ISSUE-03: 启动后台 keepalive 嗅探（默认 6h 一次，提前发现上游改版自愈），幂等
        (self._action_sniffer or action_sniffer).start_keepalive()
        log.info("nanobanana 号池加载 %d 账号", len(self.accounts))

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        sniffer = self._action_sniffer or action_sniffer
        sniffer.stop_keepalive()
        if self._action_sniffer is None:
            await sniffer.aclose()

    async def _async_load_accounts(self) -> list[dict]:
        """_load_accounts 的 async 入口：P2-3 后 account_pool.get 已 async，直接 await。

        委托给 self._load_accounts（测试通过 monkeypatch 该方法注入 mock 号池）。
        """
        return await self._load_accounts()

    async def _load_accounts(self) -> list[dict]:
        from ..account_pool import account_pool

        # P2-3: account_pool.get 已 async（aiosqlite），直接 await
        accs = await account_pool.get("nanobanana")
        # M1(审计修复): 生产进程过滤 mock 残留账号，防测试号泄漏上线
        if not MOCK_REGISTER:
            accs = [a for a in accs if a.get("cookie") != "mock-session" and "mock" not in (a.get("note") or "")]
        return accs

    async def _async_next_account(self) -> dict:
        """_next_account 的 async 入口：号池加载走 await 不阻塞 loop。

        委托给 self._next_account（内部 self.accounts / self._acc_idx 突变在
        单次 await 调用内完成，generate 串行调用无并发竞争）。
        """
        return await self._next_account()

    async def _next_account(self) -> dict:
        self.accounts = await self._load_accounts()
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

        # P2-3: total_credits 已 async（aiosqlite），直接 await
        return await account_pool.total_credits("nanobanana")

    async def health(self) -> dict:
        """健康摘要：额外暴露 Action Sniffer 缓存/嗅探状态（ISSUE-03）。"""
        out = await super().health()
        sniffer = self._action_sniffer or action_sniffer
        out["action_sniffer"] = sniffer.status()
        return out

    # ── 生成（Next.js Server Action）───────────────
    def _rsc_encode(self, obj: dict) -> str:
        """RSC 编码 JSON：'$' 开头的字符串需转义为 '$$'（逆向确认）。"""
        s = json.dumps(obj, ensure_ascii=False)
        return s.replace("$", "$$") if "$" in s else s

    async def generate(
        self,
        model: str,
        prompt: str,
        aspect_ratio: str,
        images: list[bytes] | None = None,
        resolution: str = "1K",
        download: bool = False,
        **kw,
    ) -> GenerationResult:
        if not self._client:
            return GenerationResult(status="error", error="nanobanana 未启动")
        acc = await self._async_next_account()
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
            # IMP-18: 连续限流 → 降级追踪（仅做计数与标记，不触发跨提供商自动路由）
            if self._registry_ref:
                self._registry_ref.record_failure(self.prefix)
                self._registry_ref.mark_exhausted(self.prefix, acc.get("email", "?"))
            return GenerationResult(status="error", error=str(e))
        except ProviderError as e:
            return GenerationResult(status="error", error=str(e))
        except Exception as e:
            return GenerationResult(status="error", error=f"nanobanana 生成失败: {str(e)[:120]}")
        # v6.5.1: 生成成功 → 扣减该账号积分 + 累计消耗/出图次数画像（若该账号可定位）。
        # 仅当 acc 是真实号池账号（非 mock）才落库，避免测试号污染统计。
        if acc.get("email") and acc.get("cookie") != "mock-session":
            try:
                cost = image_credit_cost(upstream, resolution, task_type="edit" if images else None)
                from ..account_pool import account_pool

                # consume_credits 同步 sqlite3+Lock → async 包装走 to_thread 不阻塞 loop
                await account_pool.async_consume_credits("nanobanana", acc["email"], cost)
            except Exception as e:
                log.warning("nanobanana 扣减积分失败 %s: %s", acc.get("email"), e)
        return GenerationResult(status="completed", asset_url=asset_url)

    def _action_headers(self, cookie: str, action_id: str) -> dict:
        return {
            "Cookie": cookie,
            "Next-Action": action_id,
            "Accept": "text/x-component",
            "Content-Type": "text/plain;charset=UTF-8",
            "Next-Router-State-Tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22zh%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%5D%2Cnull%2Cnull%2Ctrue",
        }

    async def _submit_image(self, cookie, upstream, prompt, aspect_ratio, resolution) -> str:
        body = [
            {
                "prompt": prompt,
                "model": upstream,
                "aspectRatio": aspect_ratio,
                "resolution": resolution,
                "outputFormat": "png",
                "googleSearch": False,
                "grokQualityMode": "fast",
            }
        ]
        r = await self._post_with_self_heal(_KIND_GENERATE, cookie, body)
        return await self._parse_action_response(r)

    async def _submit_edit(self, cookie, upstream, prompt, aspect_ratio, images) -> str:
        # 图生图：先上传（multipart file + model）→ 拿 /api/assets/{id}/preview → 作为 imageUrls
        up = await self._client.post(
            f"{self.base_url}/api/upload/nano-banana",
            headers={"Cookie": cookie, "User-Agent": config.USER_AGENT},
            files={"file": ("edit.png", images[0], "image/png")},
            data={"model": upstream},
        )
        if up.status_code != 200:
            raise ProviderError(f"nanobanana 上传失败: {up.status_code} {up.text[:120]}")
        url = (up.json() or {}).get("url")
        if not url:
            raise ProviderError(f"nanobanana 上传响应缺 url: {up.text[:120]}")
        body = [
            {
                "prompt": prompt,
                "model": upstream,
                "imageUrls": [url],
                "aspectRatio": aspect_ratio,
                "resolution": "1K",
                "outputFormat": "png",
                "googleSearch": False,
                "grokQualityMode": "fast",
            }
        ]
        r = await self._post_with_self_heal(_KIND_EDIT, cookie, body)
        return await self._parse_action_response(r)

    async def _get_action(self, kind: str, *, force_refresh: bool = False) -> str:
        """经 ActionSniffer 动态解析 Action ID（嗅探失败时回退静态兜底）。"""
        sniffer = self._action_sniffer or action_sniffer
        return await sniffer.get_action_id(kind, force_refresh=force_refresh)

    async def _post_with_self_heal(self, kind: str, cookie: str, body: list) -> httpx.Response:
        """提交 Server Action；遇 404 / Action 不匹配时 force_refresh 嗅探并自愈重试一次。"""
        action_id = await self._get_action(kind)
        r = await self._client.post(
            f"{self.base_url}/zh", headers=self._action_headers(cookie, action_id), content=self._rsc_encode(body)
        )
        if is_stale_action_response(r):
            log.warning("nanobanana %s Action 失配(%s)，触发嗅探自愈", kind, r.status_code)
            fresh_id = await self._get_action(kind, force_refresh=True)
            if fresh_id and fresh_id != action_id:
                r = await self._client.post(
                    f"{self.base_url}/zh",
                    headers=self._action_headers(cookie, fresh_id),
                    content=self._rsc_encode(body),
                )
        return r

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
            r = await self._client.get(f"{self.base_url}/api/tasks/{task_id}", headers={"Cookie": cookie})
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
