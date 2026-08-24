import asyncio
import re
import time
import uuid
import httpx

from api import config, turnstile_client
from api.account_pool import account_pool
from api.registerer import NanobananaRegisterer, _browser_headers, _th


async def run_and_save_one():
    # 1. 22.do 创建纯净邮箱 (type=random, 剔除 + 和多余的 .)
    headers_22do = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Origin": "https://22.do",
        "Referer": "https://22.do/",
    }
    client_22do = httpx.AsyncClient(timeout=15.0, headers=headers_22do)
    email = None
    for _ in range(10):
        r = await client_22do.post("https://22.do/action/mailbox/create", json={"type": "random"})
        em = (r.json().get("data") or {}).get("email", "")
        if em and "+" not in em and em.count(".") == 1:
            email = em
            break
    print(f"[1] Email: {email}")
    if not email:
        return "FAIL: no email"

    # 登录 22.do
    await client_22do.post(
        "https://22.do/action/mailbox/login",
        json={"email": email, "language": "en-US"},
    )
    tok_r = await client_22do.post(
        "https://22.do/action/mailbox/applyToken",
        json={"email": email, "uuid": uuid.uuid4().hex},
    )
    jwt = ((tok_r.json() or {}).get("data") or {}).get("token")

    # 2. 求解 turnstile
    reg = NanobananaRegisterer()
    captcha, dur = await turnstile_client.solve_turnstile(
        config.CF_SOLVER_URL, reg.turnstile_page, reg.SITEKEY, 60.0
    )
    print(f"[2] Captcha solved in {dur:.1f}s")

    # 3. 注册
    password = f"Tf@{email[:8]}"
    r = await _th(
        reg.client.post,
        f"{reg.base}/api/auth/sign-up/email",
        headers={
            **_browser_headers(reg.base, f"{reg.base}/zh"),
            "x-turnstile-token": captcha,
        },
        json={
            "email": email,
            "password": password,
            "name": "TfUser",
            "callbackURL": "/zh",
        },
    )
    print(f"[3] Sign-up status: {r.status_code}")
    if r.status_code != 200:
        return f"FAIL: sign-up {r.status_code}"

    # 4. 轮询收信并拉取详情
    print("[4] Polling for email...")
    link = None
    for i in range(15):
        await asyncio.sleep(4)
        mr = await client_22do.post(
            "https://22.do/action/mailbox/message",
            json={"email": email, "lastime": 0},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        try:
            data = (mr.json() or {}).get("data")
        except Exception:
            continue
        print(f"    [T+{(i+1)*4}s] message list: {data}")
        if isinstance(data, list) and len(data) > 0:
            # 优先从列表直接看有没有 content/html，否则拉 messageDetail
            for item in data:
                raw_str = json.dumps(item, ensure_ascii=False)
                m = re.search(r"https://[^\s\"\'<>]+/api/auth/verify-email\?token=[^&\s\"\'<>]+", raw_str)
                if m:
                    link = m.group(0).replace("&amp;", "&")
                    print(f"[4] Got link directly from list: {link}")
                    break
                mid = item.get("id") or item.get("messageId")
                if mid:
                    try:
                        det = await client_22do.post(
                            "https://22.do/action/mailbox/messageDetail",
                            json={"email": email, "id": mid},
                            headers={"Authorization": f"Bearer {jwt}"},
                        )
                        det_json = det.json() or {}
                        det_str = json.dumps(det_json, ensure_ascii=False)
                        m2 = re.search(r"https://[^\s\"\'<>]+/api/auth/verify-email\?token=[^&\s\"\'<>]+", det_str)
                        if m2:
                            link = m2.group(0).replace("&amp;", "&")
                            print(f"[4] Got link from detail: {link}")
                            break
                    except Exception as e:
                        print("detail error:", e)
            if link:
                break
    if not link:
        return "FAIL: no verify link"

    # 5. 点激活链接
    r_act = await _th(
        reg.client.get, link, headers={"User-Agent": config.USER_AGENT}
    )
    print(f"[5] Click link status: {r_act.status_code}")

    # 6. 登录拿 Cookie
    login_captcha, _ = await turnstile_client.solve_turnstile(
        config.CF_SOLVER_URL, reg.turnstile_page, reg.SITEKEY, 60.0
    )
    login = await _th(
        reg.client.post,
        f"{reg.base}/api/auth/sign-in/email",
        headers={
            **_browser_headers(reg.base, f"{reg.base}/zh"),
            "x-turnstile-token": login_captcha,
        },
        json={
            "email": email,
            "password": password,
            "callbackURL": "/zh",
        },
    )
    print(f"[6] Login status: {login.status_code}")
    cookie = "; ".join(f"{k}={v}" for k, v in login.cookies.items())

    # 7. 入库
    account_pool.add(
        "nanobanana", email, cookie, password=password, credits=4
    )
    print(f"[7] SUCCESS! Account added to DB: {email}")

    # 8. 签到测试
    bal = await reg.checkin(
        {
            "email": email,
            "cookie": cookie,
            "password": password,
            "credits": 4,
        }
    )
    print(f"[8] Checkin result: {bal}")
    return f"SUCCESS: {email}"


if __name__ == "__main__":
    res = asyncio.run(run_and_save_one())
    print("FINAL RESULT:", res)
