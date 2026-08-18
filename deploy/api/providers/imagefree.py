"""imagefree.net 提供商适配：复用既有 turnstile 池 + worker 引擎链路。

既有实现已非常成熟（token 池 / 熔断 / 队列），此 Provider 直接委托 Engine。
model = 服务端风格预设（prompt 前缀注入），无真实多模型。
"""
from __future__ import annotations

from .. import config
from .base import CAP_IMG2IMG, CAP_TXT2IMG, GenerationResult, ModelSpec, Provider, ProviderError

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
            # 图生图走既有 edit 链路（需 main 注入 run_edit 回调）
            runner = kw.get("edit_runner")
            if runner is None:
                return GenerationResult(status="error", error="imagefree 图生图未启用")
            return await runner(model, prompt, images, download)
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
