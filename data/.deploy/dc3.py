import httpx, json, re
ck = "__Secure-better-auth.session_token=829AAkok55D32e5wgb2Y7ecamnr0pcpR.xAM3vRuhYj1VOXtnACPfZonM4afvos7imstvdGF1auE%3D"
body = json.dumps([{"captchaToken": ""}])
r = httpx.post("https://nanobanana-pro.com/zh", headers={
    "Cookie": ck, "User-Agent": "Mozilla/5.0",
    "Next-Action": "7fa3d4d28767dbc090ad4228dff062a1e20d421ce2",
    "Accept": "text/x-component", "Content-Type": "text/plain;charset=UTF-8",
}, content=body.replace("$", "$$") if "$" in body else body, timeout=30)
text = r.text
print("resp len:", len(text), "| 含0::", "0:" in text, "| reward:", "rewardAmount" in text, "| success:", '"success"' in text)
# 提取所有 0: 行
for line in text.splitlines():
    if line.strip().startswith("0:"):
        print("0: 行:", line[:200])
