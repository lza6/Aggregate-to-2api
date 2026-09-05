import asyncio

import httpx


async def check_html():
    client = httpx.AsyncClient(
        timeout=15.0,
        headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
            "Origin": "https://22.do",
            "Referer": "https://22.do/",
        },
    )
    r = await client.post(
        "https://22.do/action/mailbox/applyToken",
        json={"email": "l55x8xl00x@usdtbeta.com", "uuid": "123456"},
    )
    print("applyToken status:", r.status_code, "text:", r.text[:200])


if __name__ == "__main__":
    asyncio.run(check_html())
