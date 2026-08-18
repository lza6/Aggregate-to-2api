import httpx, uuid, re, json, sys
sys.path.insert(0, '/app')
BASE = "https://22.do"
h = {"User-Agent":"Mozilla/5.0 Chrome/150","Content-Type":"application/json"}
client = httpx.Client(proxy="http://1023701-4a2c845a:12843fee-US-t01e0a01@gate.kookeey.info:1000",
                      headers=h, timeout=15, follow_redirects=True)
r = client.post(BASE+"/action/mailbox/create", json={"type":"random"})
email = ((r.json() or {}).get("data") or {}).get("email") or ""
client.post(BASE+"/action/mailbox/login", json={"email":email,"language":"en-US"})
tr = client.post(BASE+"/action/mailbox/applyToken", json={"email":email,"uuid":uuid.uuid4().hex.replace("-","")})
tok = ((tr.json() or {}).get("data") or {}).get("token") or ""
print("箱:", email, flush=True)
# 收件：先看 message 摘要是否含 subject=Verify
mr = client.post(BASE+"/action/mailbox/message", json={"email":email,"lastime":0}, headers={"Authorization":"Bearer "+tok})
msgs = (mr.json() or {}).get("data") or []
print("邮件数:", len(msgs), flush=True)
for m in msgs[:3]:
    print("  摘要:", m if isinstance(m,dict) else str(m)[:100], flush=True)
# 试 inbox 页面含 mid（新箱有邮件时应能在页面找到）
if msgs:
    mid = str(msgs[0].get("id") or msgs[0].get("_id") or msgs[0].get("messageId") or "")
    print("mid:", mid, flush=True)
    pg = client.get(BASE+"/inbox")
    # 打印页面是否含该 mid 及 viewEml 脚本
    print("inbox 含 mid:", mid in pg.text, flush=True)
    # 提取所有邮件链接
    ids = re.findall(r"'([a-f0-9]{32})'|\"([a-f0-9]{32})\"", pg.text)
    print("32位id:", [x[0] or x[1] for x in ids][:5], flush=True)
    # 打印页面尾部（可能含邮件列表 JS 模板）
    print("页面含 viewEml:", "viewEml" in pg.text, "| eml:", "eml" in pg.text, flush=True)
