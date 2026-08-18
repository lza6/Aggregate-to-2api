import httpx, json

# 用逆向确认有效的 session cookie 直接测签到（绕过 verify——账号本身有效）
ck = "__Secure-better-auth.session_token=829AAkok55D32e5wgb2Y7ecamnr0pcpR.xAM3vRuhYj1VOXtnACPfZonM4afvos7imstvdGF1auE%3D"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150", "Cookie": ck}

# 1) 余额（确认 cookie 有效）
r = httpx.get("https://nanobanana-pro.com/api/credits/balance", headers=UA, timeout=20)
print("1 余额:", r.status_code, r.text.strip()[:80])

# 2) 签到状态
r = httpx.get("https://nanobanana-pro.com/api/credits/daily-checkin/status", headers=UA, timeout=20)
print("2 状态:", r.status_code, r.text.strip()[:200])

# 3) 试不同签到端点（非 Server Action）
for path in ["/api/credits/daily-checkin/claim", "/api/credits/daily-checkin",
             "/api/credits/checkin", "/api/credits/daily-checkin/claim?"]:
    try:
        rr = httpx.post("https://nanobanana-pro.com" + path, headers={**UA, "Content-Type": "application/json"},
                        json={}, timeout=20)
        print(f"3 {path}: {rr.status_code} {rr.text.strip()[:80]}")
    except Exception as e:
        print(f"3 {path}: ERR {str(e)[:40]}")

# 4) Server Action 但带完整 cookie（含 session_data）
ck_full = ck + "; __Secure-better-auth.session_data=eyJzZXNzaW9uIjp7InNlc3Npb24iOnsiaWQiOiJHeDRuSTdpVXkwZUJuVXp1Ykd1NVpHeVBlN1lqMXhnMSIsImV4cGlyZXNBdCI6IjIwMjYtMDgtMjFUMjM6MDY6MDYuODYwWiIsInRva2VuIjoiODI5QUFrb2s1NUQzMmU1d2diMlk3ZWNhbW5yMHBjcFIiLCJjcmVhdGVkQXQiOiIyMDI2LTA4LTE0VDIzOjA2OjA2Ljg2MFoiLCJ1cGRhdGVkQXQiOiIyMDI2LTA4LTE0VDIzOjA2OjA2Ljg2MFoiLCJpcEFkZHJlc3MiOiI1MS4xNS4yMzcuMTkyIiwidXNlckFnZW50IjoiTW96aWxsYS81LjAgKFdpbmRvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzE1MC4wLjAuMCBTYWZhcmkvNTM3LjM2IiwidXNlcklkIjoiUk9RbGM5eXNnQk5DcFRnQm9xMVhCb2JrMUJQMmo1RmUiLCJpbXBlcnNvbmF0ZWRCeSI6bnVsbH0sInVzZXIiOnsiaWQiOiJST1FsYzl5c2dCTkNwVGdCb3ExWEJvYmsxQlAyajVGZSIsIm5hbWUiOiJDbGF1ZGU0IiwiZW1haWwiOiJyYWRlbmk2MDM1QGh1dGRvdC5jb20iLCJlbWFpbFZlcmlmaWVkIjp0cnVlLCJpbWFnZSI6bnVsbCwiY3JlYXRlZEF0IjoiMjAyNi0wOC0xNFQyMzowNTozNy4yNzVaIiwidXBkYXRlZEF0IjoiMjAyNi0wOC0xNFQyMzowNTozNy4yNzVaIiwicm9sZSI6InVzZXIiLCJiYW5uZWQiOmZhbHNlLCJiYW5SZWFzb24iOm51bGwsImJhbkV4cGlyZXMiOm51bGwsIm5vcm1hbGl6ZWRFbWFpbCI6InJhZGVuaTYwMzVAaHV0ZG90LmNvbSIsImN1c3RvbWVySWQiOm51bGx9fSwiZXhwaXJlc0F0IjoxNzg2NzUyMzY2OTE1LCJzaWduYXR1cmUiOiJZRTQtMjdUTHVVeW5GNEF6VzRhOVdUMURpVmFJcjUwLVU3ZnJ3aXpxR1I4In0="
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150", "Cookie": ck_full}
body = json.dumps([{"captchaToken": ""}])
# 尝试不同的 Next-Action（可能签到 Action 与抓包时不同）
for action in ["7fa3d4d28767dbc090ad4228dff062a1e20d421ce2", "7f5a7898dc55b3d6030ac91fb511530561237119a7"]:
    rr = httpx.post("https://nanobanana-pro.com/zh", headers={
        **H, "Next-Action": action, "Accept": "text/x-component",
        "Content-Type": "text/plain;charset=UTF-8",
        "Next-Router-State-Tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22zh%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%5D%2Cnull%2Cnull%2Ctrue",
    }, content=body, timeout=30)
    has_zero = "0:" in rr.text
    print(f"4 action {action[:10]}: {rr.status_code} len={len(rr.text)} 含0:={has_zero}")
    if has_zero:
        for line in rr.text.splitlines():
            if line.strip().startswith("0:") and "reward" in line:
                print("  签到结果行:", line[:150])
                break

# 5) 签到后再查余额
r = httpx.get("https://nanobanana-pro.com/api/credits/balance", headers=UA, timeout=20)
print("5 签到后余额:", r.text.strip()[:80])