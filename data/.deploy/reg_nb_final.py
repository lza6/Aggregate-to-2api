import asyncio, httpx, time, re, json, sys, uuid, os
sys.path.insert(0, '/app')
BTC = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150","Content-Type":"application/json","Origin":"https://nanobanana-pro.com","Referer":"https://nanobanana-pro.com/zh"}
TMH = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150","Content-Type":"application/json","Origin":"https://temp-mail.org","Referer":"https://temp-mail.org/"}

async def main():
    # 1 建 temp-mail 箱（重试 5 次应对间歇 429）
    tm = None
    for attempt in range(5):
        r = httpx.post("https://web2.temp-mail.org/mailbox", json={}, headers=TMH, timeout=20)
        if r.status_code == 200:
            tm = r.json(); break
        print(f"temp-mail 429 第{attempt+1}次，退避30s...", flush=True)
        time.sleep(30)
    if not tm: print("FAIL temp-mail"); return
    email, token = tm["mailbox"], tm["token"]
    print(f"1 箱: {email}", flush=True)
    # 2 kookeey 代理解 turnstile
    from api.kookeey import kookeey_proxy_for
    import api.turnstile_client as tc
    kk = kookeey_proxy_for(email)
    try:
        captcha = await tc.solve_turnstile("http://cfsolver:8001","https://nanobanana-pro.com/zh","0x4AAAAAACBMF7NSqVf-BSmE",90,proxy=kk)
    except Exception as e:
        print(f"3 captcha fail: {e}", flush=True); return
    print(f"2 captcha OK ({len(captcha)})", flush=True)
    # 3 sign-up
    password = "Tf@" + str(int(time.time()))
    r = httpx.post("https://nanobanana-pro.com/api/auth/sign-up/email", headers={**BTC,"x-turnstile-token":captcha},
                   json={"email":email,"password":password,"name":"TfUser","callbackURL":"/zh"}, timeout=30)
    if r.status_code != 200: print(f"3 sign-up fail: {r.status_code} {r.text[:80]}", flush=True); return
    print(f"3 sign-up 200", flush=True)
    # 4 轮询 temp-mail 收 verify（最长 300s）
    got = None
    for i in range(150):
        mm = httpx.get("https://web2.temp-mail.org/messages", headers={"Authorization":"Bearer "+token}, timeout=20)
        if mm.status_code != 200: time.sleep(2); continue
        msgs = mm.json()
        if isinstance(msgs, dict): msgs = msgs.get("messages") or msgs.get("data") or []
        for m in (msgs or []):
            if "verify-email" in json.dumps(m.get("bodyPreview","") or ""):
                got = m; break
        if got: break
        if i % 15 == 0: print(f"  轮询 {i*2}s...", flush=True)
        time.sleep(2)
    if not got: print("4 NO verify (300s)", flush=True); return
    print(f"4 verify 到达", flush=True)
    # 5 取完整正文（含 bodyHtml 链接）
    mid = str(got.get("_id") or got.get("id") or "")
    if mid:
        det = httpx.get(f"https://web2.temp-mail.org/messages/{mid}", headers={"Authorization":"Bearer "+token}, timeout=20)
        if det.status_code == 200: got = det.json()
    blob = json.dumps(got, ensure_ascii=False)
    m = re.search(r"https://[^\s\"'<>]+/api/auth/verify-email\?token=[^&\s\"'<>]+", blob)
    if not m: print("5 正文无 verify 链接", flush=True); return
    link = m.group(0).replace("&amp;","&")
    print(f"5 链接 {link[:60]}...", flush=True)
    # 6 点验证链接
    v = httpx.get(link, headers={"User-Agent":"Mozilla/5.0"}, timeout=20, follow_redirects=False)
    print(f"6 点击链接: {v.status_code}", flush=True)
    # 7 登录拿 session
    login = httpx.post("https://nanobanana-pro.com/api/auth/sign-in/email", headers=BTC,
                       json={"email":email,"password":password,"callbackURL":"/zh"}, timeout=30)
    ck = ";".join(f"{k}={v}" for k,v in login.cookies.items()) if login.cookies else ""
    has_session = "__Secure-better-auth.session_token" in ck
    print(f"7 登录: {login.status_code} | session: {has_session}", flush=True)
    if has_session:
        bal = httpx.get("https://nanobanana-pro.com/api/credits/balance", headers={"Cookie":ck,"User-Agent":"Mozilla/5.0"}, timeout=20)
        print(f"8 余额: {bal.text.strip()}", flush=True)
        # 入号池
        from api.account_pool import account_pool
        account_pool.add("nanobanana", email, ck, password, credits=4)
        print(f"9 已入号池 ✓", flush=True)
asyncio.run(main())
