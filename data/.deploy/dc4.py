import httpx, json, re
ck = "__Secure-better-auth.session_token=829AAkok55D32e5wgb2Y7ecamnr0pcpR.xAM3vRuhYj1VOXtnACPfZonM4afvos7imstvdGF1auE%3D; __Secure-better-auth.session_data=eyJzZXNzaW9uIjp7InNlc3Npb24iOnsiaWQiOiJHeDRuSTdpVXkwZUJuVXp1Ykd1NVpHeVBlN1lqMXhnMSIsImV4cGlyZXNBdCI6IjIwMjYtMDgtMjFUMjM6MDY6MDYuODYwWiIsInRva2VuIjoiODI5QUFrb2s1NUQzMmU1d2diMlk3ZWNhbW5yMHBjcFIiLCJjcmVhdGVkQXQiOiIyMDI2LTA4LTE0VDIzOjA2OjA2Ljg2MFoiLCJ1cGRhdGVkQXQiOiIyMDI2LTA4LTE0VDIzOjA2OjA2Ljg2MFoiLCJpcEFkZHJlc3MiOiI1MS4xNS4yMzcuMTkyIiwidXNlckFnZW50IjoiTW96aWxsYS81LjAgKFdpbmRvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzE1MC4wLjAuMCBTYWZhcmkvNTM3LjM2IiwidXNlcklkIjoiUk9RbGM5eXNnQk5DcFRnQm9xMVhCb2JrMUJQMmo1RmUiLCJpbXBlcnNvbmF0ZWRCeSI6bnVsbH0sInVzZXIiOnsiaWQiOiJST1FsYzl5c2dCTkNwVGdCb3ExWEJvYmsxQlAyajVGZSIsIm5hbWUiOiJDbGF1ZGU0IiwiZW1haWwiOiJyYWRlbmk2MDM1QGh1dGRvdC5jb20iLCJlbWFpbFZlcmlmaWVkIjp0cnVlLCJpbWFnZSI6bnVsbCwiY3JlYXRlZEF0IjoiMjAyNi0wOC0xNFQyMzowNTozNy4yNzVaIiwidXBkYXRlZEF0IjoiMjAyNi0wOC0xNFQyMzowNTozNy4yNzVaIiwicm9sZSI6InVzZXIiLCJiYW5uZWQiOmZhbHNlLCJiYW5SZWFzb24iOm51bGwsImJhbkV4cGlyZXMiOm51bGwsIm5vcm1hbGl6ZWRFbWFpbCI6InJhZGVuaTYwMzVAaHV0ZG90LmNvbSIsImN1c3RvbWVySWQiOm51bGx9fSwiZXhwaXJlc0F0IjoxNzg2NzUyMzY2OTE1LCJzaWduYXR1cmUiOiJZRTQtMjdUTHVVeW5GNEF6VzRhOVdUMURpVmFJcjUwLVU3ZnJ3aXpxR1I4In0="
BTC = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150","Content-Type":"application/json","Origin":"https://nanobanana-pro.com","Referer":"https://nanobanana-pro.com/zh"}
# 先看 sign-in 后 status
st = httpx.get("https://nanobanana-pro.com/api/credits/daily-checkin/status", headers={"Cookie":ck}, timeout=20)
print("status:", st.text.strip()[:150])
# Server Action 补全头
body = json.dumps([{"captchaToken": ""}])
h = {
    "Cookie": ck, "User-Agent": BTC["User-Agent"],
    "Next-Action": "7fa3d4d28767dbc090ad4228dff062a1e20d421ce2",
    "Accept": "text/x-component",
    "Content-Type": "text/plain;charset=UTF-8",
    "Next-Router-State-Tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22zh%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%5D%2Cnull%2Cnull%2Ctrue",
    "Origin": "https://nanobanana-pro.com", "Referer": "https://nanobanana-pro.com/zh",
}
r = httpx.post("https://nanobanana-pro.com/zh", headers=h, content=body.replace("$", "$$") if "$" in body else body, timeout=30)
print("action:", r.status_code, "len:", len(r.text), "| 0::", "0:" in r.text)
for line in r.text.splitlines():
    if line.strip().startswith("0:"):
        print("0: 行:", line[:250])
