import asyncio, httpx, time, re, json, sys
sys.path.insert(0, '/app')
from api.kookeey import kookeey_proxy_for
import api.turnstile_client as tc
BTC = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150","Content-Type":"application/json","Origin":"https://nanobanana-pro.com","Referer":"https://nanobanana-pro.com/zh"}
TMH = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150","Content-Type":"application/json","Origin":"https://temp-mail.org","Referer":"https://temp-mail.org/"}
GOOD_DOMAINS = ("beiwoh.com", "hutdot.com")

async def main():
    # 循环建箱直到拿到能收 verify 的域
    tm = None
    for attempt in range(15):
        kk_tm = kookeey_proxy_for(f"mt{int(time.time())}{attempt}@x.com")
        try:
            r = httpx.post("https://web2.temp-mail.org/mailbox", json={}, headers=TMH, proxy=kk_tm, timeout=25)
            if r.status_code == 200:
                d = r.json()
                dom = str(d.get("mailbox","")).split("@")[-1]
                if dom in GOOD_DOMAINS:
                    tm = d
                    print(f"✓ 命中能收verify域 {dom}（第{attempt+1}次）", flush=True)
                    break
                print(f"  域 {dom} 不是目标，重试({attempt+1}/15)", flush=True)
        except Exception as e:
            print(f"  attempt {attempt} err {str(e)[:40]}", flush=True)
        await asyncio.sleep(15)
    if not tm:
        print("FAIL 未拿到目标域", flush=True); return
    email, token = tm["mailbox"], tm["token"]
    kk = kookeey_proxy_for(email)
    captcha = await tc.solve_turnstile("http://cfsolver:8001","https://nanobanana-pro.com/zh","0x4AAAAAACBMF7NSqVf-BSmE",90,proxy=kk)
    print("captcha OK", flush=True)
    password = "Tf@" + str(int(time.time()))
    r = httpx.post("https://nanobanana-pro.com/api/auth/sign-up/email", headers={**BTC,"x-turnstile-token":captcha},
                   json={"email":email,"password":password,"name":"TfUser","callbackURL":"/zh"}, timeout=30, proxy=kk)
    print("sign-up:", r.status_code, flush=True)
    if r.status_code != 200: return
    got = None
    for i in range(300):
        try:
            mm = httpx.get("https://web2.temp-mail.org/messages", headers={"Authorization":"Bearer "+token}, proxy=kk, timeout=20)
            if mm.status_code == 200:
                msgs = mm.json()
                if isinstance(msgs, dict): msgs = msgs.get("messages") or msgs.get("data") or []
                for m in (msgs or []):
                    if "verify-email" in json.dumps(m.get("bodyPreview","") or ""):
                        got = m; break
        except Exception:
            pass
        if got: break
        if i % 30 == 0: print(f"  轮询... {i*2}s", flush=True)
        await asyncio.sleep(2)
    if not got: print("NO verify 600s", flush=True); return
    print("verify 到达", flush=True)
    mid = str(got.get("_id") or got.get("id") or "")
    if mid:
        det = httpx.get(f"https://web2.temp-mail.org/messages/{mid}", headers={"Authorization":"Bearer "+token}, proxy=kk, timeout=20)
        if det.status_code == 200: got = det.json()
    blob = json.dumps(got, ensure_ascii=False)
    m = re.search(r"https://[^\s\"'<>]+/api/auth/verify-email\?token=[^&\s\"'<>]+", blob)
    if not m: print("正文无链接", flush=True); return
    link = m.group(0).replace("&amp;","&")
    print(f"链接 {link[:50]}", flush=True)
    v = httpx.get(link, headers={"User-Agent":"Mozilla/5.0"}, timeout=20, follow_redirects=False, proxy=kk)
    print("点击:", v.status_code, flush=True)
    login = httpx.post("https://nanobanana-pro.com/api/auth/sign-in/email", headers=BTC,
                       json={"email":email,"password":password,"callbackURL":"/zh"}, timeout=30, proxy=kk)
    ck = ";".join(f"{k}={v}" for k,v in login.cookies.items()) if login.cookies else ""
    has = "__Secure-better-auth.session_token" in ck
    print("登录:", login.status_code, "| session:", has, flush=True)
    if has:
        from api.account_pool import account_pool
        account_pool.add("nanobanana", email, ck, password, credits=4)
        print("✅ 已入号池", flush=True)
asyncio.run(main())
