import httpx, uuid, re, json, sys, time
sys.path.insert(0, '/app')
BASE = "https://22.do"
h = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150","Content-Type":"application/json"}
client = httpx.Client(headers=h, timeout=15, follow_redirects=True)
# 用已知收到 verify 的邮箱登录 22.do 取正文
email = "tov3kngptvcmp0ao9og4@fft.edu.do"
client.post(BASE+"/action/mailbox/login", json={"email":email,"language":"en-US"})
tr = client.post(BASE+"/action/mailbox/applyToken", json={"email":email,"uuid":uuid.uuid4().hex.replace("-","")})
tok = ((tr.json() or {}).get("data") or {}).get("token") or ""
# 1) 试 inbox 网页（渲染完整邮件列表+正文）
pg = client.get(BASE+"/inbox")
print(f"inbox: {len(pg.text)}b, 含verify:{'verify-email' in pg.text}, 含email:{email.split('@')[0] in pg.text}", flush=True)
# 提取所有邮件链接
links = re.findall(r'href="/mail/([a-f0-9]+)"', pg.text)
print(f"邮件链接IDs: {links[:5]}", flush=True)
if links:
    # 取第一封邮件详情
    dpg = client.get(BASE+f"/mail/{links[0]}")
    print(f"邮件详情: {len(dpg.text)}b", flush=True)
    # 提取 verify 链接
    m = re.search(r"https://[^\s\"'<>]+/api/auth/verify-email\?token=[^&\s\"'<>]+", dpg.text)
    if m:
        link = m.group(0).replace("&amp;","&")
        print(f"✅ VERIFY 链接: {link[:70]}", flush=True)
        v = httpx.get(link, headers={"User-Agent":"Mozilla/5.0"}, timeout=20, follow_redirects=False)
        print(f"点链接: {v.status_code}", flush=True)
        BTC = {"User-Agent":"Mozilla/5.0 Chrome/150","Content-Type":"application/json","Origin":"https://nanobanana-pro.com","Referer":"https://nanobanana-pro.com/zh"}
        login = httpx.post("https://nanobanana-pro.com/api/auth/sign-in/email", headers=BTC,
            json={"email":email,"password":"Tf@12345678","callbackURL":"/zh"}, timeout=30)
        ck = ";".join(f"{k}={v}" for k,v in login.cookies.items()) if login.cookies else ""
        has = "__Secure-better-auth.session_token" in ck
        print(f"登录: {login.status_code} | session: {has}", flush=True)
        if has:
            bal = httpx.get("https://nanobanana-pro.com/api/credits/balance", headers={"Cookie":ck,"User-Agent":"Mozilla/5.0"}, timeout=20)
            print(f"余额: {bal.text.strip()}", flush=True)
            from api.account_pool import account_pool
            account_pool.add("nanobanana", email, ck, "Tf@12345678", credits=4)
            print("✅ 已入号池", flush=True)
    else:
        # 从页面搜索 verify 相关文字
        body = re.search(r'<body[^>]*>(.*?)</body>', dpg.text, re.S)
        if body:
            text = re.sub(r'<[^>]+>', ' ', body.group(1))
            text = re.sub(r'\s+', ' ', text).strip()[:500]
            print(f"  正文片段: {text[:300]}", flush=True)
else:
    print("inbox 无邮件链接", flush=True)
