import asyncio, httpx, time, re, json
HTML = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150","Content-Type":"application/json","Origin":"https://temp-mail.org","Referer":"https://temp-mail.org/"}
BTC = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150","Content-Type":"application/json","Origin":"https://nanobanana-pro.com","Referer":"https://nanobanana-pro.com/zh"}

async def main():
    tm = httpx.post("https://web2.temp-mail.org/mailbox", json={}, headers=HTML, timeout=20).json()
    email, token = tm["mailbox"], tm["token"]
    print("1 temp-mail box:", email)
    import sys; sys.path.insert(0, '/app')
    from api.kookeey import kookeey_proxy_for
    import api.turnstile_client as tc
    kk = kookeey_proxy_for(email)
    print("2 kookeey:", kk[:60])
    try:
        captcha = await tc.solve_turnstile("http://cfsolver:8001","https://nanobanana-pro.com/zh","0x4AAAAAACBMF7NSqVf-BSmE",90,proxy=kk)
        print("3 captcha len:", len(captcha))
    except Exception as e:
        print("3 captcha fail:", str(e)[:80]); return
    r = httpx.post("https://nanobanana-pro.com/api/auth/sign-up/email", headers={**BTC,"x-turnstile-token":captcha},
                   json={"email":email,"password":"Tf@12345678","name":"TfUser","callbackURL":"/zh"}, timeout=30)
    print("4 sign-up:", r.status_code, r.text[:80])
    got = None
    for i in range(45):
        mm = httpx.get("https://web2.temp-mail.org/messages", headers={"Authorization":f"Bearer {token}"}, timeout=20)
        msgs = mm.json() if mm.status_code==200 else []
        if isinstance(msgs, dict): msgs = msgs.get("messages") or msgs.get("data") or []
        for m in (msgs or []):
            blob = json.dumps(m, ensure_ascii=False)
            if "Verify" in blob or "verify-email" in blob:
                got = m; break
        if got: break
        time.sleep(2)
    if got:
        blob = json.dumps(got, ensure_ascii=False)
        m = re.search(r"https://[^\s\"'<>]+/api/auth/verify-email\?token=[^&\s\"'<>]+", blob)
        print("5 got verify:", bool(m), (m.group(0)[:70].replace('&amp;','&') if m else ""))
        if m:
            link = m.group(0).replace('&amp;','&')
            v = httpx.get(link, headers={"User-Agent":"Mozilla/5.0"}, timeout=20, follow_redirects=False)
            print("6 click link:", v.status_code)
            login = httpx.post("https://nanobanana-pro.com/api/auth/sign-in/email", headers=BTC,
                               json={"email":email,"password":"Tf@12345678","callbackURL":"/zh"}, timeout=30)
            ck = ";".join(f"{k}={v}" for k,v in login.cookies.items()) if login.cookies else ""
            print("7 login:", login.status_code, "| session:", "__Secure-better-auth.session_token" in ck)
    else:
        print("5 NO verify email")
asyncio.run(main())
