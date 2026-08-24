import asyncio
import uuid
import httpx


async def check_raw():
    email = "l55x8xl00x@usdtbeta.com"
    client = httpx.AsyncClient(
        timeout=15.0,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Origin": "https://22.do",
            "Referer": "https://22.do/",
        },
    )
    await client.post(
        "https://22.do/action/mailbox/login",
        json={"email": email, "language": "en-US"},
    )
    tok_r = await client.post(
        "https://22.do/action/mailbox/applyToken",
        json={"email": email, "uuid": uuid.uuid4().hex},
    )
    jwt = ((tok_r.json() or {}).get("data") or {}).get("token")
    mr = await client.post(
        "https://22.do/action/mailbox/message",
        json={"email": email, "lastime": 0},
        headers={"Authorization": f"Bearer {jwt}"},
    )
    print("MESSAGES_NOW:", mr.json())


if __name__ == "__main__":
    asyncio.run(check_raw())
