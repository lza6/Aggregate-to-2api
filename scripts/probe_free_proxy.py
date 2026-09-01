import sys
sys.path.insert(0, "/app")
import asyncio, httpx
from api.proxy_pool import proxy_pool
from api.free_proxy_fetcher import free_proxy_fetcher

async def probe():
    await free_proxy_fetcher.start()
    try:
        stats = await free_proxy_fetcher._fetch_once()
        print("injected:", stats.get("injected"), "| pool:", len(proxy_pool.entries))
        url = await proxy_pool.acquire(prefer_source="free")
        print("acquired:", url)
        if url:
            body = {"prompt": "probe", "aspect_ratio": "1:1", "turnstile_token": "x"}
            async with httpx.AsyncClient(proxy=url, timeout=25) as c:
                r = await c.post("https://imagefree.net/api/generate", json=body)
                print("via-proxy:", r.status_code, r.text[:80])
            async with httpx.AsyncClient(timeout=25) as c2:
                r2 = await c2.post("https://imagefree.net/api/generate", json=body)
                print("direct:", r2.status_code, r2.text[:80])
    finally:
        await free_proxy_fetcher.stop()

asyncio.run(probe())