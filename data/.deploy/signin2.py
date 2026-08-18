import httpx, json, re

# 逆向 nanobanana 签到 Action：先抓取页面 RSC 流看 claimDailyCheckinAction 的完整调用方式
# 方法：GET /zh 拿 self.__next_f 里的 Server Reference 参数（actionId + body 结构）
ck = "__Secure-better-auth.session_token=829AAkok55D32e5wgb2Y7ecamnr0pcpR.xAM3vRuhYj1VOXtnACPfZonM4afvos7imstvdGF1auE%3D"
h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150", "Cookie": ck}
r = httpx.get("https://nanobanana-pro.com/zh", headers=h, timeout=30)
text = r.text
print("页面 len:", len(text))
# 找 claimDailyCheckinAction 或 Server Reference
for kw in ["claimDailyCheckin", "daily-checkin", "captchaToken", "checkin"]:
    i = text.find(kw)
    if i >= 0:
        print(f"含 {kw}: 位置 {i} 上下文: {text[max(0,i-60):i+80]}")
        break
# 找 Next-Action 相关
for m in re.finditer(r"[a-f0-9]{40}", text):
    print("40hex:", m.group(0)[:20])
    break
# 直接试 known action 带 callbackURL
body = json.dumps([{"captchaToken": "", "callbackURL": "/zh"}])
H = {**h, "Next-Action": "7fa3d4d28767dbc090ad4228dff062a1e20d421ce2",
     "Accept": "text/x-component", "Content-Type": "text/plain;charset=UTF-8"}
rr = httpx.post("https://nanobanana-pro.com/zh", headers=H, content=body.replace("$", "$$") if "$" in body else body, timeout=30)
# 提取真正的 RSC 行（含 success）
for line in rr.text.splitlines():
    ls = line.strip()
    if ls.startswith("0:"):
        # 尝试找 rewardAmount 或 success
        if "reward" in ls or "success" in ls or "error" in ls:
            print("0: 行:", ls[:200])
            break
    if ls.startswith("1:"):
        print("1: 行:", ls[:100])
        break
bal = httpx.get("https://nanobanana-pro.com/api/credits/balance", headers=h, timeout=20)
print("余额:", bal.text.strip()[:60])