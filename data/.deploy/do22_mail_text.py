import httpx, uuid, re, json, sys
sys.path.insert(0, '/app')
BASE = "https://22.do"
h = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150","Content-Type":"application/json"}
client = httpx.Client(headers=h, timeout=15, follow_redirects=True)
r = client.post(BASE+"/action/mailbox/create", json={"type":"random"})
email = ((r.json() or {}).get("data") or {}).get("email") or ""
client.post(BASE+"/action/mailbox/login", json={"email":email,"language":"en-US"})
tr = client.post(BASE+"/action/mailbox/applyToken", json={"email":email,"uuid":uuid.uuid4().hex})
tok = ((tr.json() or {}).get("data") or {}).get("token") or ""
# 访 inbox 拿邮件列表
pg = client.get(BASE+"/inbox")
# 从 HTML 提取邮件 ID
ids = re.findall(r'data-message-id="([^"]+)"', pg.text)
if not ids:
    ids = re.findall(r'/mail/([a-f0-9]+)', pg.text)
print(f"邮件数: {len(ids)}", flush=True)
if ids:
    # 访第一封详情
    dpg = client.get(BASE+f"/mail/{ids[0]}")
    print(f"详情页: {len(dpg.text)}b, verify:{'verify-email' in dpg.text}", flush=True)
    # 提取 verify 链接
    link = re.search(r"https://[^\s\"'<>]+/api/auth/verify-email\?token=[^&\s\"'<>]+", dpg.text)
    if link:
        print(f"VERIFY 链接: {link.group(0).replace('&amp;','&')[:80]}", flush=True)
    else:
        print("详情页无 verify 链接，搜 body:", flush=True)
        # 提取页面正文
        body = re.search(r'<body[^>]*>(.*?)</body>', dpg.text, re.S)
        if body:
            text = re.sub(r'<[^>]+>', ' ', body.group(1))
            text = re.sub(r'\s+', ' ', text).strip()[:300]
            print(f"  正文: {text}", flush=True)
