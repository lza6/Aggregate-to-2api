import httpx, uuid, re
BASE = "https://22.do"
h = {"User-Agent": "Mozilla/5.0 Chrome/150", "Content-Type": "application/json"}
client = httpx.Client(headers=h, timeout=15, follow_redirects=True)
r = client.post(BASE + "/action/mailbox/create", json={"type": "random"})
email = ((r.json() or {}).get("data") or {}).get("email") or ""
client.post(BASE + "/action/mailbox/login", json={"email": email, "language": "en-US"})
tr = client.post(BASE + "/action/mailbox/applyToken", json={"email": email, "uuid": uuid.uuid4().hex.replace("-", "")})
tok = ((tr.json() or {}).get("data") or {}).get("token") or ""
pg = client.get(BASE + "/inbox")
t = pg.text
print("inbox len:", len(t), "email:", email)
for m in re.finditer(r"https://[^\s\"'<>]+/api/auth/verify-email\?token=[^&\s\"'<>]+", t):
    print("VERIFY:", m.group(0).replace("&amp;", "&")[:80]); break
else:
    print("无 verify 链接")
ids = re.findall(r"data-message-id=['\"]([^'\"]+)", t)
print("data-message-id:", ids[:5])
ids2 = re.findall(r"['\"]([a-f0-9]{32})['\"]", t)
print("32hex:", ids2[:5])
# 搜正文关键词
for kw in ["verify-email", "verify", "Confirm", "confirm"]:
    i = t.lower().find(kw)
    if i >= 0:
        print(f"含 {kw}: 位置 {i}, 上下文: {t[max(0,i-30):i+50]}")
        break
# 搜 viewEml 调用
for m in re.finditer(r"viewEml\(([^)]+)\)", t):
    print("viewEml(", m.group(1)[:60], ")")
    break