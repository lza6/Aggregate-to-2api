import asyncio, httpx, time, re, json, sys
sys.path.insert(0, '/app')
from api.email_pool import Do22Source
from api.kookeey import kookeey_proxy_for
import api.turnstile_client as tc
BTC = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150","Content-Type":"application/json","Origin":"https://nanobanana-pro.com","Referer":"https://nanobanana-pro.com/zh"}

async def main():
    s = Do22Source()
    email, st = s.new_address()
    print("1 22.do box:", email)
    kk = kookeey_proxy_for(email)
    print("2 kookeey:", kk[:55])
    try:
        captcha = await tc.solve_turnstile("http://cfsolver:8001","https://nanobanana-pro.com/zh","0x4AAAAAACBMF7NSqVf-BSmE",90,proxy=kk)
        print("3 captcha len:", len(captcha))
    except Exception as e:
        print("3 captcha fail:", str(e)[:70]); return
    r = httpx.post("https://nanobanana-pro.com/api/auth/sign-up/email", headers={**BTC,"x-turnstile-token":captcha},
                   json={"email":email,"password":"Tf@12345678","name":"TfUser","callbackURL":"/zh"}, timeout=30)
    print("4 sign-up:", r.status_code, r.text[:70])
    got = None
    for i in range(45):
        mails = s.fetch_mails(email, st)
        for m in (mails or []):
            blob = json.dumps(m, ensure_ascii=False)
            if "Verify" in blob or "verify-email" in blob:
                got = m; break
        if got: break
        time.sleep(2)
    if got:
        blob = json.dumps(got, ensure_ascii=False)
        m = re.search(r"https://[^\s\"'<>]+/api/auth/verify-email\?token=[^&\s\"'<>]+", blob)
        print("5 got verify:", bool(m), (m.group(0)[:60].replace('&amp;','&') if m else ""))
        if m:
            link = m.group(0).replace('&amp;','&')
            v = httpx.get(link, headers={"User-Agent":"Mozilla/5.0"}, timeout=20, follow_redirects=False)
            print("6 click:", v.status_code)
            login = httpx.post("https://nanobanana-pro.com/api/auth/sign-in/email", headers=BTC,
                               json={"email":email,"password":"Tf@12345678","callbackURL":"/zh"}, timeout=30)
            ck = ";".join(f"{k}={v}" for k,v in login.cookies.items()) if login.cookies else ""
            print("7 login:", login.status_code, "| session:", "__Secure-better-auth.session_token" in ck)
    else:
        print("5 NO verify on 22.do")
asyncio.run(main())
