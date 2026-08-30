import asyncio
import httpx
import re
import time
from api.turnstile_client import solve_turnstile
from api import config
from api.account_pool import account_pool


async def main():
    c = httpx.AsyncClient(
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        }
    )

    # 1. 建箱
    print("1. Creating temp-mail.io mailbox...")
    cr = await c.post(
        "https://api.internal.temp-mail.io/api/v3/email/new", json={"min_name_length": 10, "max_name_length": 10}
    )
    email = cr.json().get("email")
    print(f"1. Got email: {email}")

    # 2. 求解 Turnstile
    print("2. Solving Turnstile...")
    captcha, _ = await solve_turnstile(
        config.CF_SOLVER_URL, "https://nanobanana-pro.com/zh", "0x4AAAAAACBMF7NSqVf-BSmE", 60.0
    )
    print(f"2. Solved captcha: {captcha[:20]}")

    # 3. 提交注册
    print("3. Submitting sign-up...")
    password = "Tf@Pass" + str(int(time.time()))
    reg_r = await c.post(
        "https://nanobanana-pro.com/api/auth/sign-up/email",
        headers={
            "Origin": "https://nanobanana-pro.com",
            "Referer": "https://nanobanana-pro.com/zh",
            "x-turnstile-token": captcha,
        },
        json={"email": email, "password": password, "name": "TfUser", "callbackURL": "/zh"},
    )
    print("3. Sign-up status:", reg_r.status_code, reg_r.text)
    if reg_r.status_code != 200:
        return

    # 4. 等待验证邮件
    print("4. Waiting for mail on temp-mail.io...")
    link = None
    for attempt in range(30):
        await asyncio.sleep(2)
        mr = await c.get(f"https://api.internal.temp-mail.io/api/v3/email/{email}/messages")
        if mr.status_code == 200:
            msgs = mr.json()
            if msgs and isinstance(msgs, list) and len(msgs) > 0:
                body = msgs[0].get("body_html") or msgs[0].get("body_text") or ""
                print(f"Found message! Body length: {len(body)}")
                m = re.findall(r'https://[^\s"\'<>]+/api/auth/verify-email\?token=[^\s"\'<>]+', body)
                if m:
                    link = m[0].replace("&amp;", "&")
                    print(f"5. Extracted verify link: {link}")
                    break
    if not link:
        print("No verify link received within timeout")
        return

    # 5. 点击验证链接
    print("5. Clicking verify link...")
    vr = await c.get(link)
    print(f"Verify link clicked, status: {vr.status_code}")

    # 6. 求解并登录
    print("6. Solving login Turnstile...")
    login_captcha, _ = await solve_turnstile(
        config.CF_SOLVER_URL, "https://nanobanana-pro.com/zh", "0x4AAAAAACBMF7NSqVf-BSmE", 60.0
    )
    login_r = await c.post(
        "https://nanobanana-pro.com/api/auth/sign-in/email",
        headers={
            "Origin": "https://nanobanana-pro.com",
            "Referer": "https://nanobanana-pro.com/zh",
            "x-turnstile-token": login_captcha,
        },
        json={"email": email, "password": password, "callbackURL": "/zh"},
    )
    print("Login response status:", login_r.status_code, "cookies:", dict(login_r.cookies))

    if "__Secure-better-auth.session_token" in login_r.cookies:
        cookie_str = "; ".join([f"{k}={v}" for k, v in login_r.cookies.items()])
        account_pool.add("nanobanana", email, cookie_str, password, 4)
        print("7. SUCCESS! Registered and Added to DB! Total accounts:", len(account_pool.get("nanobanana")))
    else:
        print("Failed to acquire session token")


if __name__ == "__main__":
    asyncio.run(main())
