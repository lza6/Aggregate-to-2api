import httpx, json, sys
sys.path.insert(0, '/app')
# 用 httpx.Client（会话保持 cookie）经 kookeey 代理访问 temp-mail
client = httpx.Client(headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150",
                               "Content-Type":"application/json",
                               "Origin":"https://temp-mail.org","Referer":"https://temp-mail.org/"},
                      timeout=20, follow_redirects=True)
# 建箱
r = client.post("https://web2.temp-mail.org/mailbox", json={})
print("建箱:", r.status_code, r.text[:80])
if r.status_code == 200:
    d = r.json()
    email = d.get("mailbox"); token = d.get("token")
    # messages 用同一 session(cookie) + token
    mm = client.get("https://web2.temp-mail.org/messages", headers={"Authorization":f"Bearer {token}"})
    print("messages:", mm.status_code, str(mm.text)[:80])
    print("session cookies:", [c.name for c in client.cookies])
