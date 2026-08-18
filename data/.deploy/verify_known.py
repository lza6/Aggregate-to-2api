import httpx, uuid, re, json, sys, time
sys.path.insert(0, '/app')
# 22.do 邮箱（已知收到 verify 的）：tov3kngptvcmp0ao9og4@fft.edu.do
# 密码：Tf@12345678（但那是 22.do 的密码，不是 nanobanana 密码。sign-up 时用的密码得查到）
# 那次 sign-up 用的是 nbf.py 注册的，密码 Tf@12345678
# 重查该邮箱 verify 链接
BASE = "https://22.do"; h = {"User-Agent":"Mozilla/5.0 Chrome/150","Content-Type":"application/json","Origin":BASE,"Referer":BASE+"/"}
email = "tov3kngptvcmp0ao9og4@fft.edu.do"
httpx.post(BASE+"/action/mailbox/login", json={"email":email,"language":"en-US"}, headers=h, timeout=15)
tr = httpx.post(BASE+"/action/mailbox/applyToken", json={"email":email,"uuid":uuid.uuid4().hex}, headers=h, timeout=15)
tok = ((tr.json() or {}).get("data") or {}).get("token") or ""
# 1) 试 message/read 看能否取正文
mr = httpx.post(BASE+"/action/mailbox/message/read", json={"email":email,"id":"f4d3fe9bdcc6baae625dece32df6df79"}, headers={**h,"Authorization":"Bearer "+tok}, timeout=15)
print("message/read:", mr.status_code, str(mr.text)[:200])
# 2) 试 message/detail
mr2 = httpx.post(BASE+"/action/mailbox/message/detail", json={"email":email,"id":"f4d3fe9bdcc6baae625dece32df6df79"}, headers={**h,"Authorization":"Bearer "+tok}, timeout=15)
print("message/detail:", mr2.status_code, str(mr2.text)[:200])
# 3) 试 ff 接口
import json as j
for path in ["/action/mailbox/message/read", "/action/mailbox/message/detail", "/action/mailbox/message/body"]:
    r = httpx.post(BASE+path, json={"email":email,"id":"f4d3fe9bdcc6baae625dece32df6df79"}, headers={**h,"Authorization":"Bearer "+tok}, timeout=10)
    if r.status_code == 200:
        data = r.json().get("data") or {}
        if isinstance(data, list) and data:
            has_body = any(k in data[0] for k in ["text","html","body","content","bodyHtml"])
            print(f"{path.split('/')[-1]}: has_body={has_body}, keys={list(data[0].keys()) if isinstance(data[0],dict) else type(data[0])}")
