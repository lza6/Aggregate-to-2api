import httpx, json, re
ck = "__Secure-better-auth.session_token=829AAkok55D32e5wgb2Y7ecamnr0pcpR.xAM3vRuhYj1VOXtnACPfZonM4afvos7imstvdGF1auE%3D"
body = json.dumps([{"captchaToken": ""}])
h = {"Cookie": ck, "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150",
    "Next-Action": "7fa3d4d28767dbc090ad4228dff062a1e20d421ce2",
    "Accept": "text/x-component", "Content-Type": "text/plain;charset=UTF-8",
    "Next-Router-State-Tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22zh%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%5D%2Cnull%2Cnull%2Ctrue",
    "Origin": "https://nanobanana-pro.com", "Referer": "https://nanobanana-pro.com/zh"}
r = httpx.post("https://nanobanana-pro.com/zh", headers=h, content=body.replace("$", "$$") if "$" in body else body, timeout=30)
# 从 self.__next_f 提取 RSC payload
for m in re.finditer(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', r.text, re.S):
    payload = m.group(1).replace("\u003C", "<").replace("\u003E", ">").replace("\u0022", '"').replace('\\"', '"')
    payload = payload.encode().decode('unicode_escape')
    for line in payload.split("\n"):
        line = line.strip()
        if line.startswith("0:"):
            print("0: 行:", line[:200])
            break
# 直接查余额
bal = httpx.get("https://nanobanana-pro.com/api/credits/balance", headers={"Cookie": ck}, timeout=20)
print("余额:", bal.text.strip()[:80])
