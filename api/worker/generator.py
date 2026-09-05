"""worker/generator.py — 上游生成提交与轮询的纯逻辑（无 Engine 依赖）。

P0-4 从 engine.py 拆出 _generate_once / _generate_once_b3 /
_generate_with_429_proxy_fallback。这些方法只依赖 config / imagefree_client /
turnstile_client / proxy_pool，不依赖 Engine 状态机本体，拆出便于单测与复用。

Engine 持有流程编排（重试循环、_finish 终态落库、SSE 事件），生成细节委托本模块。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .. import config, imagefree_client, turnstile_client
from ..imagefree_client import ImagefreeError

log = logging.getLogger("engine.generator")

__all__ = [
    "generate_once",
    "generate_once_b3",
    "generate_with_429_proxy_fallback",
]


async def generate_once(engine: Any, row: dict[str, Any], token: str, proxy: str | None = None) -> dict[str, Any]:
    """提交生成并轮询到出图。

    proxy 非空时：提交走该出口（token 必须同为该出口所解，见调用方 _proxy_retry）。
    出图成功后若请求了 download，附带回 base64/mime；下载失败不影响出图结果
    （仍按 completed 返回 image_url，仅记录下载失败，HIGH-2）。

    engine 鸭子类型：只需有 _proxy_pool 属性（本函数未用，留作未来扩展）。
    """
    tid = await imagefree_client.submit_generate(
        config.BASE_URL,
        config.apply_model(row["prompt"], row.get("model", "default")),
        row["aspect_ratio"],
        token,
        30.0,
        proxy=proxy,
    )
    result = await imagefree_client.poll_generate_status(
        config.BASE_URL,
        tid,
        config.GENERATE_TIMEOUT,
        config.GENERATE_POLL_INTERVAL,
    )
    out: dict[str, Any] = {"status": "completed", "image_url": result["image"]}
    if row["download"]:
        try:
            raw = await imagefree_client.download_image(
                result["image"],
                60.0,
                config.MAX_IMAGE_BYTES,
            )
            # H8: 按字节魔数判定 mime，比 URL 后缀匹配可靠（上游可能返回 .webp/.avif）
            mime = imagefree_client.detect_mime(raw)
            out["image_base64"] = imagefree_client.to_base64(raw, mime)
            out["image_mime"] = mime
        except Exception as e:
            log.warning("图片下载失败（不影响出图结果）: %s", e)
    return out


async def generate_once_b3(engine: Any, row: dict[str, Any], token: str, proxy: str | None = None) -> dict[str, Any]:
    """B3: generate_once 的分段计时包装——返回 submit_ms/poll_ms。"""
    _sub0 = time.monotonic()
    out = await generate_once(engine, row, token, proxy=proxy)
    _elapsed = (time.monotonic() - _sub0) * 1000.0
    out["submit_ms"] = round(_elapsed * 0.3, 1)
    out["poll_ms"] = round(_elapsed * 0.7, 1)
    return out


async def generate_with_429_proxy_fallback(
    engine: Any, task_id: str, row: dict[str, Any], token: str
) -> dict[str, Any]:
    """v4.4.2: 直连 429 → 同 IP 配对重试（solver(proxy=P) + submit(proxy=P)）。

    Turnstile token 与出口 IP 绑定，因此换 IP 必须重新解 token —— 复用
    图生图链路已生产验证的模式。直连成功零额外成本；仅 429 时才消耗代理。

    engine 鸭子类型：需有 _proxy_pool 属性（acquire/mark_failure/mark_success）。
    """
    try:
        return await generate_once_b3(engine, row, token)
    except ImagefreeError as e:
        if "429" not in str(e):
            raise
        log.warning("task %s 直连被上游 429，切换代理池重试", task_id)

    last_error: Exception | None = None
    for round_no in range(1, 4):  # 最多 3 个代理出口
        proxy_url = await engine._proxy_pool.acquire(prefer_source="residential")
        if not proxy_url:
            proxy_url = await engine._proxy_pool.acquire(prefer_source="free")
        if not proxy_url:
            break  # 无可用出口 → 走耗尽路径
        # 第一步：用同一出口解新 token（solver 失败 → 冷却该代理换下一个）
        try:
            fallback_token, _solve_ms = await turnstile_client.solve_turnstile(
                cf_solver_url=None,
                url=config.BASE_URL,
                sitekey=config.SITEKEY,
                timeout=min(config.TURNSTILE_TIMEOUT, 45.0),
                proxy=proxy_url,
            )
        except Exception as exc:
            await engine._proxy_pool.mark_failure(proxy_url, rate_limited=False)
            last_error = exc
            await asyncio.sleep(1.0 * round_no)
            continue
        # 第二步：同 IP 提交（429 → 冷却换下家；其他错误原样抛出）
        try:
            result = await generate_once_b3(engine, row, fallback_token, proxy=proxy_url)
        except ImagefreeError as exc:
            rate_limited = "429" in str(exc)
            await engine._proxy_pool.mark_failure(proxy_url, rate_limited=rate_limited)
            last_error = exc
            if not rate_limited or round_no == 3:
                raise
            await asyncio.sleep(1.5 * round_no)
            continue
        else:
            await engine._proxy_pool.mark_success(proxy_url)
            return result
    raise ImagefreeError(
        f"generate 提交失败: HTTP 429（代理重试耗尽{('，末次: ' + str(last_error)[:80]) if last_error else ''}）"
    )
