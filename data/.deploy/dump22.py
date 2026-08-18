import httpx, uuid, json, sys
sys.path.insert(0, '/app')
BASE = "https://22.do"
h = {"User-Agent":"Mozilla/5.0 Chrome/150","Content-Type":"application/json","Origin":BASE,"Referer":BASE+"/"}
email = "tov3kngptvcmp0ao9og4@fft.edu.do"
httpx.post(BASE+"/action/mailbox/login", json={"email":email,"language":"en-US"}, headers=h, timeout=15)
tr = httpx.post(BASE+"/action/mailbox/applyToken", json={"email":email,"uuid":uuid.uuid4().hex}, headers=h, timeout=15)
tok = ((tr.json() or {}).get("data") or {}).get("token") or ""
mr = httpx.post(BASE+"/action/mailbox/message", json={"email":email,"lastime":0}, headers={**h,"Authorization":"Bearer "+tok}, timeout=15)
data = (mr.json() or {}).get("data") or []
print("共", len(data), "封；最新一封字段:")
if data:
    last = data[-1]
    for k, v in last.items():
        if isinstance(v, str) and len(v) > 50:
            print(f"  {k}: {v[:200]}")
        else:
            print(f"  {k}: {v}")
