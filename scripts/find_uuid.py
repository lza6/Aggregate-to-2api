import asyncio
import re

import httpx


async def test_uuid():
    client = httpx.AsyncClient(
        timeout=15.0,
        headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
            "Origin": "https://22.do",
            "Referer": "https://22.do/",
        },
    )
    r = await client.get("https://22.do")
    scripts = re.findall(r'src=["\']([^"\']+\.js)["\']', r.text)
    for s in scripts:
        url = s if s.startswith("http") else "https://22.do" + s
        js = await client.get(url)
        if "applyToken" in js.text:
            print("FOUND in", url)
            idx = js.text.find("applyToken")
            print(js.text[max(0, idx - 100) : idx + 300])


if __name__ == "__main__":
    asyncio.run(test_uuid())
