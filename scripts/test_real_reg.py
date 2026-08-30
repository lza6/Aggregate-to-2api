import asyncio
import httpx
import re
import time
from api.turnstile_client import solve_turnstile
from api import config
from api.account_pool import account_pool


async def main():
    session = httpx.AsyncClient(
        headers={
            "User-Agent": config.USER_AGENT,
            "Origin": "https://temp-mail.org",
            "Referer": "https://temp-mail.org/",
        }
    )
    print("1. Creating temp-mail mailbox...")
    tr = await session.post("https://web2.temp-mail.org/mailbox", json={})
    if tr.status_code != 200:
        print("Temp-mail create failed:", tr.status_code, tr.text[:100])
        return
    data = tr.json()
    email = data.get("mailbox")
    token = data.get("token")
    print(f"1. Got email: {email}")

    print("2. Solving Turnstile...")
    captcha, _ = await solve_turnstile(
        config.CF_SOLVER_URL, "https://nanobanana-pro.com/zh", "0x4AAAAAACBMF7NSqVf-BSmE", 60.0
    )
    print(f"2. Solved captcha: {captcha[:20]}")

    print("3. Submitting sign-up...")
    password = "Tf@Pass" + str(int(time.time()))
    reg_r = await session.post(
        "https://nanobanana-pro.com/api/auth/sign-up/email",
        headers={
            "Origin": "https://nanobanana-pro.com",
            "Referer": "https://nanobanana-pro.com/zh",
            "x-turnstile-token": captcha,
        },
        json={"email": email, "password": password, "name": "TfUser", "callbackURL": "/zh"},
    )
    print("3. Sign-up response:", reg_r.status_code, reg_r.text)
    if reg_r.status_code != 200:
        return

    print("4. Waiting for verify email...")
    link = None
    for attempt in range(30):
        await asyncio.sleep(2)
        mr = await session.get("https://web2.temp-mail.org/messages", headers={"Authorization": f"Bearer {token}"})
        if mr.status_code == 200:
            msgs = mr.json()
            if msgs and isinstance(msgs, list):
                mid = msgs[0].get("_id")
                print(f"Found message id: {mid}")
                det_r = await session.get(
                    f"https://web2.temp-mail.org/messages/{mid}", headers={"Authorization": f"Bearer {token}"}
                )
                if det_r.status_code == 200:
                    bHtml = det_r.json().get("bodyHtml", "")
                    m = re.findall(r'https://[^\s"\'<>]+/api/auth/verify-email\?token=[^\s"\'<>]+', bHtml)
                    if m:
                        link = m[0].replace("&amp;", "&")
                        print("Found verify link:", link)
                        break
    if not link:
        print("No verify link received within timeout")
        return

    print("5. Visiting verify link...")
    vr = await session.get(link)
    print("Verify response status:", vr.status_code)

    print("6. Solving login Turnstile...")
    login_captcha, _ = await solve_turnstile(
        config.CF_SOLVER_URL, "https://nanobanana-pro.com/zh", "0x4AAAAAACBMF7NSqVf-BSmE", 60.0
    )
    login_r = await session.post(
        "https://nanobanana-pro.com/api/auth/sign-in/email",
        headers={
            "Origin": "https://nanobanana-pro.com",
            "Referer": "https://nanobanana-pro.com/zh",
            "x-turnstile-token": login_captcha,
        },
        json={"email": email, "password": password, "callbackURL": "/zh"},
    )
    print("Login status:", login_r.status_code, "cookies:", dict(login_r.cookies))

    cookie_str = "; ".join([f"{k}={v}" for k, v in login_r.cookies.items()])
    if "__Secure-better-auth.session_token" in login_r.cookies:
        account_pool.add("nanobanana", email, cookie_str, password, 4)
        print("7. SUCCESS! Added account to DB. Total active accounts:", len(account_pool.get("nanobanana")))
    else:
        print("Failed to get session cookie")


if __name__ == "__main__":
    asyncio.run(main())
