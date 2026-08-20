"""缓存预热：启动时异步加载常见查询到缓存，避免启动后空窗期首次请求慢。"""
import logging

log = logging.getLogger("cache_warmup")


async def warmup_cache(gallery_cache, db) -> dict[str, int]:
    """预热常见缓存条目，返回 {key: 是否成功(1/0)} 统计。

    各步骤独立 try/except，失败不影响其他预热。
    预热内容包括：
    - 统计概览（stats:overview）
    - 近日统计（stats:daily:14）
    - 月度统计（stats:monthly:12）
    - 画廊常见 limit（gallery:10, gallery:20, gallery:50）
    """
    result: dict[str, int] = {}

    # 1. 统计概览
    try:
        overview = await db.stats_overview()
        await gallery_cache.set("stats:overview", overview)
        result["stats:overview"] = 1
    except Exception as e:
        log.warning("缓存预热 stats:overview 失败: %s", e)
        result["stats:overview"] = 0

    # 2. 近日统计
    try:
        daily = await db.stats_daily(14)
        await gallery_cache.set("stats:daily:14", daily)
        result["stats:daily:14"] = 1
    except Exception as e:
        log.warning("缓存预热 stats:daily:14 失败: %s", e)
        result["stats:daily:14"] = 0

    # 3. 月度统计
    try:
        monthly = await db.stats_monthly(12)
        await gallery_cache.set("stats:monthly:12", monthly)
        result["stats:monthly:12"] = 1
    except Exception as e:
        log.warning("缓存预热 stats:monthly:12 失败: %s", e)
        result["stats:monthly:12"] = 0

    # 4. 画廊常见 limit（与 /v1/gallery 端点格式一致）
    for limit in (10, 20, 50):
        key = f"gallery:{limit}"
        try:
            items = await db.recent_images(limit)
            out = []
            for t in items:
                out.append({
                    "image_url": t["image_url"],
                    "image_mime": t.get("image_mime"),
                    "prompt": t["prompt"],
                    "aspect_ratio": t["aspect_ratio"],
                    "duration_sec": t["duration_sec"],
                    "finished_at": t["finished_at"],
                })
            await gallery_cache.set(key, {"items": out, "count": len(out)})
            result[key] = 1
        except Exception as e:
            log.warning("缓存预热 %s 失败: %s", key, e)
            result[key] = 0

    total_ok = sum(1 for v in result.values() if v)
    log.info("缓存预热完成: %d/%d 成功", total_ok, len(result))
    return result