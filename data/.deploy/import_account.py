import sqlite3, time, os, sys
sys.path.insert(0, '/app')
# 从逆向资料导入已知 nanobanana 账号
DB = "/app/data/account_pool.db"
accounts = [
    {"email": "radeni6035@hutdot.com", "cookie": "__Secure-better-auth.session_token=829AAkok55D32e5wgb2Y7ecamnr0pcpR.xAM3vRuhYj1VOXtnACPfZonM4afvos7imstvdGF1auE%3D; __Secure-better-auth.session_data=eyJzZXNzaW9uIjp7InNlc3Npb24iOnsiaWQiOiJHeDRuSTdpVXkwZUJuVXp1Ykd1NVpHeVBlN1lqMXhnMSIsImV4cGlyZXNBdCI6IjIwMjYtMDgtMjFUMjM6MDY6MDYuODYwWiIsInRva2VuIjoiODI5QUFrb2s1NUQzMmU1d2diMlk3ZWNhbW5yMHBjcFIiLCJjcmVhdGVkQXQiOiIyMDI2LTA4LTE0VDIzOjA2OjA2Ljg2MFoiLCJ1cGRhdGVkQXQiOiIyMDI2LTA4LTE0VDIzOjA2OjA2Ljg2MFoiLCJpcEFkZHJlc3MiOiI1MS4xNS4yMzcuMTkyIiwidXNlckFnZW50IjoiTW96aWxsYS81LjAgKFdpbmRvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzE1MC4wLjAuMCBTYWZhcmkvNTM3LjM2IiwidXNlcklkIjoiUk9RbGM5eXNnQk5DcFRnQm9xMVhCb2JrMUJQMmo1RmUiLCJpbXBlcnNvbmF0ZWRCeSI6bnVsbH0sInVzZXIiOnsiaWQiOiJST1FsYzl5c2dCTkNwVGdCb3ExWEJvYmsxQlAyajVGZSIsIm5hbWUiOiJDbGF1ZGU0IiwiZW1haWwiOiJyYWRlbmk2MDM1QGh1dGRvdC5jb20iLCJlbWFpbFZlcmlmaWVkIjp0cnVlLCJpbWFnZSI6bnVsbCwiY3JlYXRlZEF0IjoiMjAyNi0wOC0xNFQyMzowNTozNy4yNzVaIiwidXBkYXRlZEF0IjoiMjAyNi0wOC0xNFQyMzowNTozNy4yNzVaIiwicm9sZSI6InVzZXIiLCJiYW5uZWQiOmZhbHNlLCJiYW5SZWFzb24iOm51bGwsImJhbkV4cGlyZXMiOm51bGwsIm5vcm1hbGl6ZWRFbWFpbCI6InJhZGVuaTYwMzVAaHV0ZG90LmNvbSIsImN1c3RvbWVySWQiOm51bGx9fSwiZXhwaXJlc0F0IjoxNzg2NzUyMzY2OTE1LCJzaWduYXR1cmUiOiJZRTQtMjdUTHVVeW5GNEF6VzRhOVdUMURpVmFJcjUwLVU3ZnJ3aXpxR1I4In0=", "password": "", "credits": 0},
]
c = sqlite3.connect(DB)
now = time.time()
for a in accounts:
    c.execute("INSERT OR REPLACE INTO accounts (provider,email,password,cookie,credits,status,created_at,updated_at,note) VALUES (?,?,?,?,?,?,?,?,?)",
              ("nanobanana", a["email"], a["password"], a["cookie"], a["credits"], "ok", now, now, "imported"))
    print(f"导入: {a['email']} credits={a['credits']}")
c.commit()
cnt = c.execute("SELECT COUNT(*) FROM accounts WHERE provider='nanobanana' AND status='ok'").fetchone()[0]
print(f"号池 nanobanana 现有: {cnt} 个")
c.close()
