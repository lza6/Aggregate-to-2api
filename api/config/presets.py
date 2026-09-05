"""模型风格预设、宽高比常量、请求体上限等纯常量与工具函数。

P0-2（v8.0）：从 `api/config/__init__.py` 拆分出来——这些常量与 `apply_model` 工具函数
不依赖 Settings 实例（纯字面量 + dict + 字符串拼接），独立成模块便于 dispatch/worker/
imagefree/health/models 等消费方按需 import，也使 __init__.py 聚焦于 Settings 类与单例。

向后兼容：`from api.config import MAX_IMAGE_BYTES / apply_model / MODEL_PRESETS /
ASPECT_RATIOS / MAX_PROMPT_LEN` 旧路径仍可用（__init__.py 顶部 re-export）。
"""

from __future__ import annotations

# ── 请求体上限（防恶意大 base64 正文）────────────────────────
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_PROMPT_LEN = 2000

# ── 宽高比 → 分辨率映射 ──────────────────────────────────
ASPECT_RATIOS: dict[str, str] = {
    "1:1": "1024x1024",
    "3:4": "768x1024",
    "4:3": "1024x768",
    "9:16": "576x1024",
    "16:9": "1024x576",
}

# ── 模型风格预设 ─────────────────────────────────────────
MODEL_PRESETS: dict[str, dict] = {
    "default": {
        "name": "默认",
        "description": "不注入任何风格，原样提交提示词",
        "prefix": "",
        "applies_to": ["txt2img", "img2img"],
    },
    "anime": {
        "name": "动漫",
        "description": "日系动漫插画风格，高完成度线稿与上色",
        "prefix": "anime style, high quality anime illustration, vibrant colors, detailed lineart, ",
        "applies_to": ["txt2img"],
    },
    "realistic": {
        "name": "写实摄影",
        "description": "超写实照片质感，高细节、电影级光影",
        "prefix": "photorealistic, ultra detailed, 8k, cinematic lighting, sharp focus, ",
        "applies_to": ["txt2img"],
    },
    "watercolor": {
        "name": "水彩",
        "description": "水彩画风格，柔和晕染、通透层次",
        "prefix": "watercolor painting style, soft washes, delicate brushwork, translucent layers, ",
        "applies_to": ["txt2img", "img2img"],
    },
    "ink": {
        "name": "水墨",
        "description": "中国传统水墨画风，留白、写意、淡雅",
        "prefix": "traditional chinese ink wash painting style, minimalist, elegant negative space, ",
        "applies_to": ["txt2img"],
    },
    "cyberpunk": {
        "name": "赛博朋克",
        "description": "赛博朋克霓虹风格，未来都市、强对比色调",
        "prefix": "cyberpunk neon style, futuristic city, neon glow, high contrast, ",
        "applies_to": ["txt2img", "img2img"],
    },
}


def apply_model(prompt: str, model: str) -> str:
    """模型风格预设 → prompt 前缀注入（default 不加前缀）。供 worker/main 共用。"""
    prefix = MODEL_PRESETS.get(model, {}).get("prefix", "")
    return prefix + prompt if prefix else prompt


__all__ = [
    "MAX_IMAGE_BYTES",
    "MAX_PROMPT_LEN",
    "ASPECT_RATIOS",
    "MODEL_PRESETS",
    "apply_model",
]
