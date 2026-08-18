import asyncio, httpx, time, re, json, sys
sys.path.insert(0, '/app')
from api.email_pool import TempMailSource
from api.kookeey import kookeey_proxy_for
import api.turnstile_client as tc
BTC = {"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/150","Content-Type":"application/json","Origin":"https://nanobanana-pro.com","Referer":"https://nanobanana-pro.com/zh"}
TH = {"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/150","Origin":"https://temp-mail.org","Referer":"https://temp-mail.org/"}

async def main():
    s = TempMailSource()
    email, st = s.new_address()
    print("1 temp-mail box:", email)
    kk = kookeey_proxy_for(email)
    print("2 kookeey:", kk[:55])
    captcha = await tc.solve_turnstile("http://cfsolver:8001","https://nanobanana-pro.com/zh","0x4AAAAAACBMF7NSqVf-BSmE",90,proxy=kk)
    print("3 captcha len:", len(captcha))
    r = httpx.post("https://nanobanana-pro.com/api/auth/sign-up/email", headers={**BTC,"x-turnstile-token":captcha},
                   json={"email":email,"password":"Tf@12345678","name":"TfUser","callbackURL":"/zh"}, timeout=30)
    print("4 sign-up:", r.status_code, r.text[:60])
    got = None
    tok = st.get("token")
    for i in range(120):  # 300s
        mm = httpx.get("https://web2.temp-mail.org/messages", headers={"Authorization":"Bearer "+tok}, timeout=20)
        msgs = mm.json() if mm.status_code==200 else []
        if isinstance(msgs, dict): msgs = msgs.get("messages") or msgs.get("data") or []
        for m in (msgs or []):
            blob = json.dumps(m, ensure_ascii=False)
            if "verify-email" in blob or "Verify" in json.dumps(m.get("subject","")):
                got = m
                break
        if got:
            # 拉完整正文（含 bodyHtml/bodyPreview）
            mid = str(got.get("_id") or got.get("id") or "")
            if mid:
                det = httpx.get("https://web2.temp-mail.org/messages/"+mid, headers={"Authorization":"Bearer "+tok}, timeout=20)
                if det.status_code == 200:
                    got = det.json()
            break
        time.sleep(2)
    if got:
        blob = json.dumps(got, ensure_ascii=False)
        m = re.search(r"https://[^\s\"'<>]+/api/auth/verify-email\?token=[^&\s\"'<>]+", blob)
        print("5 got verify:", bool(m), (m.group(0)[:70].replace('&amp;','&') if m else ""))
        if m:
            link = m.group(0).replace('&amp;','&')
            v = httpx.get(link, headers={"User-Agent":"Mozilla/5.0"}, timeout=20, follow_redirects=False)
            print("6 click:", v.status_code)
            login = httpx.post("https://nanobanana-pro.com/api/auth/sign-in/email", headers=BTC,
                               json={"email":email,"password":"Tf@12345678","callbackURL":"/zh"}, timeout=30)
            ck = ";".join(f"{k}={v}" for k,v in login.cookies.items()) if login.cookies else ""
            print("7 login:", login.status_code, "| session:", "__Secure-better-auth.session_token" in ck)
            if ck and "__Secure-better-auth.session_token" in ck:
                bal = httpx.get("https://nanobanana-pro.com/api/credits/balance", headers={"Cookie":ck,"User-Agent":"Mozilla/5.0"}, timeout=20)
                print("8 balance:", bal.text.strip())
    else:
        print("5 NO verify")
asyncio.run(main())
