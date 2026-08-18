import httpx, uuid, re, json, sys
sys.path.insert(0, '/app')
BASE = "https://22.do"
h = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150","Content-Type":"application/json","Origin":BASE,"Referer":BASE+"/"}
client = httpx.Client(headers=h, timeout=15, follow_redirects=True)
r = client.post(BASE+"/action/mailbox/create", json={"type":"random"})
email = ((r.json() or {}).get("data") or {}).get("email") or ""
client.post(BASE+"/action/mailbox/login", json={"email":email,"language":"en-US"})
tr = client.post(BASE+"/action/mailbox/applyToken", json={"email":email,"uuid":uuid.uuid4().hex})
tok = ((tr.json() or {}).get("data") or {}).get("token") or ""
print(f"箱: {email}", flush=True)
# 试网页收件箱
for path in ["/mailbox", "/inbox", "/mail", "/"]:
    pg = client.get(BASE+path)
    if pg.status_code == 200 and len(pg.text) > 300:
        print(f"{path} -> {len(pg.text)}b, 含邮箱:{email.split('@')[0] in pg.text}, verify:{'verify' in pg.text.lower()}", flush=True)
        # 提取所有邮件相关链接
        links = re.findall(r'href="([^"]+)"', pg.text)
        mail_links = [l for l in links if "/mail/" in l or "message" in l or "read" in l]
        if mail_links:
            print(f"  邮件链接: {mail_links[:5]}", flush=True)
        break
# 试 mailbox 页面
pg2 = client.get(BASE+"/mailbox")
if pg2.status_code == 200:
    print(f"mailbox: {len(pg2.text)}b, 含inbox:{'inbox' in pg2.text.lower()}", flush=True)
