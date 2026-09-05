import asyncio
import re
import time

import httpx

from api import config
from api.account_pool import account_pool
from api.turnstile_client import solve_turnstile


async def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Origin": "https://temp-mail.org",
        "Referer": "https://temp-mail.org/",
        "Accept": "application/json, text/plain, */*",
    }
    c = httpx.AsyncClient(headers=headers, timeout=20.0)

    # 1. 建箱
    print("1. Creating web2.temp-mail.org mailbox...")
    r = await c.post("https://web2.temp-mail.org/mailbox", json={})
    if r.status_code != 200:
        print("Create failed:", r.status_code, r.text)
        return
    data = r.json()
    email = data.get("mailbox")
    token = data.get("token")
    print(f"1. Mailbox: {email}")

    # 2. 求解 Turnstile
    print("2. Solving Turnstile...")
    captcha, _ = await solve_turnstile(
        config.CF_SOLVER_URL, "https://nanobanana-pro.com/zh", "0x4AAAAAACBMF7NSqVf-BSmE", 60.0
    )
    print(f"2. Solved captcha: {captcha[:20]}")

    # 3. 注册
    print("3. Submitting sign-up...")
    password = "Tf@Pass" + str(int(time.time()))
    reg_client = httpx.AsyncClient(headers={"User-Agent": config.USER_AGENT})
    reg_r = await reg_client.post(
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

    # 4. 等待邮件
    print("4. Waiting for verify mail...")
    link = None
    for i in range(25):
        await asyncio.sleep(2)
        mr = await c.get("https://web2.temp-mail.org/messages", headers={"Authorization": f"Bearer {token}"})
        if mr.status_code == 200:
            msgs = mr.json()
            if msgs and isinstance(msgs, list) and len(msgs) > 0:
                mid = msgs[0].get("_id")
                print(f"Found message ID: {mid}")
                det_r = await c.get(
                    f"https://web2.temp-mail.org/messages/{mid}", headers={"Authorization": f"Bearer {token}"}
                )
                if det_r.status_code == 200:
                    body = det_r.json().get("bodyHtml", "")
                    m = re.findall(r'https://[^\s"\'<>]+/api/auth/verify-email\?token=[^\s"\'<>]+', body)
                    if m:
                        link = m[0].replace("&amp;", "&")
                        print("5. Extracted verify link:", link)
                        break
    if not link:
        print("Timeout waiting for verify link")
        return

    # 5. 点击激活
    print("5. Visiting verify link...")
    vr = await reg_client.get(link)
    print("Verify link status:", vr.status_code)

    # 6. 求解并登录
    print("6. Solving login Turnstile...")
    login_captcha, _ = await solve_turnstile(
        config.CF_SOLVER_URL, "https://nanobanana-pro.com/zh", "0x4AAAAAACBMF7NSqVf-BSmE", 60.0
    )
    login_r = await reg_client.post(
        "https://nanobanana-pro.com/api/auth/sign-in/email",
        headers={
            "Origin": "https://nanobanana-pro.com",
            "Referer": "https://nanobanana-pro.com/zh",
            "x-turnstile-token": login_captcha,
        },
        json={"email": email, "password": password, "callbackURL": "/zh"},
    )
    print("Login status:", login_r.status_code, "cookies:", dict(login_r.cookies))

    if "__Secure-better-auth.session_token" in login_r.cookies:
        cookie_str = "; ".join([f"{k}={v}" for k, v in login_r.cookies.items()])
        account_pool.add("nanobanana", email, cookie_str, password, 4)
        print(
            "7. SUCCESS! Successfully added account to database! Total accounts in DB:",
            len(account_pool.get("nanobanana")),
        )
    else:
        print("Failed to acquire session token")


if __name__ == "__main__":
    asyncio.run(main())
