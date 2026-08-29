"""imagefree.net 提供商适配：复用既有 turnstile 池 + worker 引擎链路。

既有实现已非常成熟（token 池 / 熔断 / 队列），此 Provider 直接委托 Engine。
model = 服务端风格预设（prompt 前缀注入），无真实多模型。
"""
from __future__ import annotations

import asyncio

from .. import config
from .base import GenerationResult, ModelSpec, Provider

_PRESETS = {
    "default": ("默认", "不注入任何风格，原样提交", ("txt2img", "img2img"), ""),
    "anime": ("动漫", "日系动漫插画风格，高完成度线稿与上色", ("txt2img",), "anime style, high quality anime illustration, vibrant colors, detailed lineart, "),
    "realistic": ("写实摄影", "超写实照片质感，高细节、电影级光影", ("txt2img",), "photorealistic, ultra detailed, 8k, cinematic lighting, sharp focus, "),
    "watercolor": ("水彩", "水彩画风格，柔和晕染、通透层次", ("txt2img", "img2img"), "watercolor painting style, soft washes, delicate brushwork, translucent layers, "),
    "ink": ("水墨", "中国传统水墨画风，留白、写意、淡雅", ("txt2img",), "traditional chinese ink wash painting style, minimalist, elegant negative space, "),
    "cyberpunk": ("赛博朋克", "赛博朋克霓虹风格，未来都市、强对比色调", ("txt2img", "img2img"), "cyberpunk neon style, futuristic city, neon glow, high contrast, "),
}


class ImagefreeProvider(Provider):
    prefix = "imagefree"
    display_name = "imagefree（主站）"
    base_url = config.BASE_URL
    models: dict[str, ModelSpec] = {}

    def __init__(self) -> None:
        super().__init__()
        # 懒依赖注入：main 启动后设 engine（避免循环 import）
        self.engine = None
        self._build_models()

    def _build_models(self) -> None:
        for mid, (name, desc, caps, _prefix) in _PRESETS.items():
            self.models[f"imagefree/{mid}"] = ModelSpec(
                id=f"imagefree/{mid}",
                provider=self.prefix,
                upstream_model=mid,
                capabilities=tuple(caps),
                display_name=name,
                description=desc,
                aspect_ratios=("1:1", "3:4", "4:3", "9:16", "16:9"),
                resolutions=(),
                credits=None,
                account_required=False,
            )

    def needs_proxy_per_request(self) -> bool:
        return False  # 走既有 token 池 + 共享连接

    async def credits(self) -> int | None:
        return None  # 理论无限免费（受控上游）

    async def generate(self, model: str, prompt: str, aspect_ratio: str,
                       images: list[bytes] | None = None, resolution: str = "1K",
                       download: bool = False, **kw) -> GenerationResult:
        if self.engine is None:
            return GenerationResult(status="error", error="imagefree 引擎未就绪")
        if images:
            # 图生图直调既有执行链（带进程内+跨进程文件锁，保障并发=1）
            runner = kw.get("edit_runner")
            if runner is not None:
                return await runner(model, prompt, images, download)
            # 未显式注入 runner 时直通内部链路
            from .. import imagefree_client
            from ..dispatch_edit import _EDIT_PROXY_POOL, _EDIT_LOCK, _acquire_edit_mutex, _release_edit_mutex
            image = images[0]
            ctype = imagefree_client.detect_mime(image)
            proxy = await _EDIT_PROXY_POOL.acquire_proxy()
            key = proxy or "default"
            local_lock = _EDIT_PROXY_POOL.lock_for(key) if proxy else _EDIT_LOCK
            try:
                async with local_lock:
                    token = await _acquire_edit_mutex(key)
                    if not token:
                        return GenerationResult(status="error", error="图生图繁忙：其他实例正在生成同一出口通道，请稍后重试")
                    try:
                        upstream_model = model.split("/", 1)[-1] if "/" in model else model
                        last_err = None
                        for attempt in range(1, config.EDIT_RETRY_MAX + 1):
                            cf_token = await self.engine.acquire_token(key=proxy or "direct")
                            if not cf_token:
                                return GenerationResult(status="error", error="人机验证 token 暂不可用，请稍后重试")
                            try:
                                public_url = await imagefree_client.upload_edit_image(
                                    config.BASE_URL, image, ctype, proxy=proxy)
                                tid = await imagefree_client.submit_edit(
                                    config.BASE_URL, public_url, config.apply_model(prompt, upstream_model), cf_token,
                                    proxy=proxy)
                                res = await imagefree_client.poll_edit_status(
                                    config.BASE_URL, tid, config.EDIT_TIMEOUT, config.GENERATE_POLL_INTERVAL,
                                    proxy=proxy)
                                break
                            except Exception as e:
                                last_err = str(e)
                                msg = last_err.lower()
                                if ("already have an image editing task" in msg or "task in progress" in msg) and attempt < config.EDIT_RETRY_MAX:
                                    await asyncio.sleep(config.EDIT_RETRY_INTERVAL)
                                    continue
                                return GenerationResult(status="error", error=f"图生图失败: {e}", proxy_used=proxy)
                        else:
                            return GenerationResult(status="error", error=f"图生图失败（重试超限）: {last_err}", proxy_used=proxy)

                        asset_url = res["image"]
                        asset_bytes = None
                        asset_mime = None
                        if download:
                            try:
                                raw = await imagefree_client.download_image(asset_url, 60.0, config.MAX_IMAGE_BYTES)
                                asset_mime = imagefree_client.detect_mime(raw)
                                asset_bytes = imagefree_client.to_base64(raw, asset_mime)
                            except Exception:
                                pass
                        return GenerationResult(status="completed", asset_url=asset_url,
                                                asset_bytes=asset_bytes, asset_mime=asset_mime,
                                                proxy_used=proxy)
                    finally:
                        _release_edit_mutex(key, token)
            finally:
                _EDIT_PROXY_POOL.release_proxy(proxy)
        # 文生图：入队 → 等待终态
        try:
            task_id = await self.engine.submit(prompt, aspect_ratio, download, model)
            task = await self.engine.wait_result(task_id, config.SYNC_TIMEOUT)
        except Exception as e:
            return GenerationResult(status="error", error=str(e))
        if task["status"] == "completed":
            return GenerationResult(
                status="completed", asset_url=task["image_url"],
                asset_bytes=task.get("image_base64"), asset_mime=task.get("image_mime"),
            )
        return GenerationResult(status="error", error=task.get("error") or "未知失败")
