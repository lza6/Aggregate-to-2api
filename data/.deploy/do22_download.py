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
# download 需要 viewId（可能是 messageId）
# 先拿 message 列表
mr = client.post(BASE+"/action/mailbox/message", json={"email":email,"lastime":0}, headers={"Authorization":"Bearer "+tok})
data = (mr.json() or {}).get("data") or []
print(f"邮件数: {len(data)}", flush=True)
if data:
    msg = data[0]
    mid = str(msg.get("id") or msg.get("_id") or msg.get("messageId") or "")
    print(f"mid: {mid}", flush=True)
    # 试 download 带 viewId
    dl = client.post(BASE+"/action/mailbox/download", json={"email":email,"viewId":mid},
                     headers={"Authorization":"Bearer "+tok})
    print(f"download: {dl.status_code} {str(dl.text)[:300]}", flush=True)
    # 试不带 viewId 单带 id
    dl2 = client.post(BASE+"/action/mailbox/download", json={"email":email,"id":mid},
                      headers={"Authorization":"Bearer "+tok})
    print(f"download(id): {dl2.status_code} {str(dl2.text)[:200]}", flush=True)
    # 试 view 带 viewId
    v = client.post(BASE+"/action/mailbox/view", json={"email":email,"viewId":mid},
                    headers={"Authorization":"Bearer "+tok})
    print(f"view: {v.status_code} {str(v.text)[:300]}", flush=True)
# 用已知有 verify 邮件的邮箱查
email2 = "tov3kngptvcmp0ao9og4@fft.edu.do"
client.post(BASE+"/action/mailbox/login", json={"email":email2,"language":"en-US"})
tr2 = client.post(BASE+"/action/mailbox/applyToken", json={"email":email2,"uuid":uuid.uuid4().hex.replace("-","")})
tok2 = ((tr2.json() or {}).get("data") or {}).get("token") or ""
# 用已知 messageId
dl3 = client.post(BASE+"/action/mailbox/download", json={"email":email2,"viewId":"f4d3fe9bdcc6baae625dece32df6df79"},
                  headers={"Authorization":"Bearer "+tok2})
print(f"download(已知messageId): {dl3.status_code} {str(dl3.text)[:500]}", flush=True)
