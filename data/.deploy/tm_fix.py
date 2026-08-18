import httpx, json, sys, time, hashlib, uuid
sys.path.insert(0, '/app')
# 每号不同 kookeey 出口 IP
email_seed = f"tm{int(time.time())}@x.com"
session = hashlib.md5(email_seed.encode()).hexdigest()[:8]
kk = f"http://1023701-4a2c845a:12843fee-US-{session}@gate.kookeey.info:1000"
# httpx.Client 经 kookeey 代理，保持 cookie
client = httpx.Client(headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150",
                               "Content-Type":"application/json",
                               "Origin":"https://temp-mail.org","Referer":"https://temp-mail.org/"},
                      proxies={"http://": kk, "https://": kk}, timeout=20, follow_redirects=True)
r = client.post("https://web2.temp-mail.org/mailbox", json={})
print("建箱:", r.status_code, r.text[:80])
if r.status_code == 200:
    d = r.json()
    email = d.get("mailbox"); token = d.get("token")
    print(f"email: {email}")
    # 同 session 查 messages
    mm = client.get("https://web2.temp-mail.org/messages", headers={"Authorization":f"Bearer {token}"})
    print("messages:", mm.status_code, str(mm.text)[:100])
