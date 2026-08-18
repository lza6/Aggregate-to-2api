import httpx, uuid, re, json, sys
sys.path.insert(0, '/app')
BASE = "https://22.do"
h = {"User-Agent":"Mozilla/5.0 Chrome/150","Content-Type":"application/json","Origin":BASE,"Referer":BASE+"/"}
email = "tov3kngptvcmp0ao9og4@fft.edu.do"
httpx.post(BASE+"/action/mailbox/login", json={"email":email,"language":"en-US"}, headers=h, timeout=15)
tr = httpx.post(BASE+"/action/mailbox/applyToken", json={"email":email,"uuid":uuid.uuid4().hex}, headers=h, timeout=15)
tok = ((tr.json() or {}).get("data") or {}).get("token") or ""
mr = httpx.post(BASE+"/action/mailbox/message", json={"email":email,"lastime":0}, headers={**h,"Authorization":"Bearer "+tok}, timeout=15)
data = (mr.json() or {}).get("data") or []
blob = json.dumps(data[-1] if data else {}, ensure_ascii=False)
m = re.search(r"https://[^\s\"'<>]+/api/auth/verify-email\?token=[^&\s\"'<>]+", blob)
print("verify link:", bool(m))
if m:
    link = m.group(0).replace("&amp;","&")
    v = httpx.get(link, headers={"User-Agent":"Mozilla/5.0"}, timeout=20, follow_redirects=False)
    print("click:", v.status_code)
    BTC = {"User-Agent":"Mozilla/5.0 Chrome/150","Content-Type":"application/json","Origin":"https://nanobanana-pro.com","Referer":"https://nanobanana-pro.com/zh"}
    login = httpx.post("https://nanobanana-pro.com/api/auth/sign-in/email", headers=BTC,
        json={"email":email,"password":"Tf@12345678","callbackURL":"/zh"}, timeout=30)
    ck = ";".join(f"{k}={v}" for k,v in login.cookies.items()) if login.cookies else ""
    print("login:", login.status_code, "| session:", "__Secure-better-auth.session_token" in ck)
    if ck and "__Secure-better-auth.session_token" in ck:
        bal = httpx.get("https://nanobanana-pro.com/api/credits/balance", headers={"Cookie":ck,"User-Agent":"Mozilla/5.0"}, timeout=20)
        print("balance:", bal.json())
