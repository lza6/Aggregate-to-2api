# 探测 temp-mail 建箱返回域的分布：建 5 箱列出域
import httpx, sys, time
sys.path.insert(0, '/app')
h={"User-Agent":"Mozilla/5.0 Chrome/150","Content-Type":"application/json","Origin":"https://temp-mail.org","Referer":"https://temp-mail.org/"}
for i in range(5):
    r=httpx.post("https://web2.temp-mail.org/mailbox", json={}, headers=h, timeout=20)
    if r.status_code==200:
        d=r.json(); print("箱", i+1, d.get("mailbox","?").split("@")[-1])
    else:
        print("箱", i+1, "429")
    time.sleep(15)
