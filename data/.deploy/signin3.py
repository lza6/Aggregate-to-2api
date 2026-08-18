import httpx, json, re

ck = "__Secure-better-auth.session_token=829AAkok55D32e5wgb2Y7ecamnr0pcpR.xAM3vRuhYj1VOXtnACPfZonM4afvos7imstvdGF1auE%3D"
h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150", "Cookie": ck}
# 从页面 RSC 流提取 Server Action 信息：找 Next-Action / actionId / claim
r = httpx.get("https://nanobanana-pro.com/zh", headers=h, timeout=30)
text = r.text
# 从 __next_f 提取所有 RSC payload 并拼接
payloads = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', text, re.S)
blob = "".join(payloads)
# 反转义
try:
    blob = blob.encode().decode('unicode_escape').encode('latin1').decode('utf-8', errors='replace')
except Exception:
    pass
print("RSC 长度:", len(blob))
for kw in ["claimDailyCheckin", "daily-checkin", "captchaToken", "Next-Action"]:
    i = blob.find(kw)
    if i >= 0:
        print(f"{kw}: {blob[max(0,i-60):i+120]}")
        break
else:
    print("未在 RSC 找到签到关键字")
# 找 actionId / action id（Server Action 约定：export const id = "..."）
for m in re.finditer(r'actionId["\s:]+([a-f0-9]{40})', blob):
    print("actionId:", m.group(1))
    break
# 找 claimDailyCheckin 的 server reference
for m in re.finditer(r'createServerReference\("([a-f0-9]{40})"', blob):
    print("serverRef:", m.group(1))
    break