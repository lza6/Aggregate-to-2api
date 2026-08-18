import httpx, uuid, re, json, sys
sys.path.insert(0, '/app')
BASE = "https://22.do"
h = {"User-Agent":"Mozilla/5.0 Chrome/150","Content-Type":"application/json"}
client = httpx.Client(headers=h, timeout=15, follow_redirects=True)
r = client.post(BASE+"/action/mailbox/create", json={"type":"random"})
email = ((r.json() or {}).get("data") or {}).get("email") or ""
client.post(BASE+"/action/mailbox/login", json={"email":email,"language":"en-US"})
tr = client.post(BASE+"/action/mailbox/applyToken", json={"email":email,"uuid":uuid.uuid4().hex.replace("-","")})
tok = ((tr.json() or {}).get("data") or {}).get("token") or ""
# 试 viewEml 可能调用的接口（取正文）
for path in ["/action/mailbox/view", "/action/mailbox/read", "/action/mailbox/body", "/action/mailbox/download",
             "/action/mailbox/message/view", "/action/mailbox/message/download",
             "/api/mail/view", "/api/mail/read"]:
    r = client.post(BASE+path, json={"email":email,"id":"test"}, headers={"Authorization":"Bearer "+tok})
    if r.status_code != 404:
        print(f"{path.split('/')[-1]}: {r.status_code} {str(r.text)[:80]}", flush=True)
# 试 viewEml GET 参数
for path in [f"/action/mailbox/view?id=test", f"/action/mailbox/read?id=test",
             f"/api/mail/view?id=test", f"/mail/view?id=test"]:
    r = client.get(BASE+path)
    if r.status_code != 404 and len(r.text) > 50:
        print(f"GET {path.split('?')[0].split('/')[-1]}: {r.status_code} {len(r.text)}b", flush=True)
# 看 temporary.js 里的 viewEml 定义（由 JS 文件提供）
js = client.get(BASE+"/assets/js/temporary.js")
if js.status_code == 200:
    m = re.search(r'viewEml[\s\S]{0,500}', js.text)
    if m:
        print(f"viewEml 定义: {m.group(0)[:300]}", flush=True)
