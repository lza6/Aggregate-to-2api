"""nanobanana 号池自动注册循环：独立后台进程，不依赖主网关 cf_solver 槽。

使用 22.do 邮箱（唯一确认能收到 nanobanana verify 的源）+ kookeey 住宅代理。
成功注册后同步写入 account_pool.db，签到循环由主网关自动处理。
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import time
import uuid
from urllib.parse import quote

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("nb_loop")

KOOKEEY = {
    "user_id": os.getenv("IF_KOOKEEY_USER_ID", "1023701"),
    "sec_user": os.getenv("IF_KOOKEEY_SEC_USER", "4a2c845a"),
    "sec_pass": os.getenv("IF_KOOKEEY_SEC_PASS", "12843fee"),
    "gate": "gate.kookeey.info", "port": 1000, "country": "US",
}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = int(os.getenv("IF_NANOBANANA_ACCOUNT_TARGET", "500"))
CF_SOLVER = os.getenv("IF_CF_SOLVER_URL", "http://127.0.0.1:8001")
DB = os.path.join(ROOT, "data", "account_pool.db")


def kk_url(email=""):
    s = hashlib.md5((email or "").strip().lower().encode()).hexdigest()[:8]
    return f"http://{KOOKEEY['user_id']}-{quote(KOOKEEY['sec_user'],safe='')}:{quote(KOOKEEY['sec_pass'],safe='')}-{KOOKEEY['country']}-{s}@{KOOKEEY['gate']}:{KOOKEEY['port']}"


def _ok_count():
    try:
        c = sqlite3.connect(DB)
        r = c.execute("SELECT COUNT(*) FROM accounts WHERE provider='nanobanana' AND status='ok'").fetchone()[0]
        c.close(); return r
    except Exception:
        return 0


def _add(email, cookie, password, credits=4):
    try:
        c = sqlite3.connect(DB)
        c.execute("INSERT OR REPLACE INTO accounts (provider,email,password,cookie,credits,status,created_at,updated_at,note)"
                  " VALUES (?,?,?,?,?,?,?,?,?)",
                  ("nanobanana", email, password, cookie, credits, "ok", time.time(), time.time(), "auto_reg"))
        c.commit(); c.close()
        log.info("已入号池: %s (总量 %d)", email, _ok_count())
    except Exception as e:
        log.warning("入池失败: %s", e)


async def register_one() -> bool:
    kk = kk_url(f"reg{int(time.time())}@x.com")
    client = httpx.Client(proxy=kk, timeout=25, follow_redirects=True,
        headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150",
                 "Content-Type":"application/json","Origin":"https://22.do","Referer":"https://22.do/"})
    email = token = None
    for _ in range(5):
        try:
            r = client.post("https://22.do/action/mailbox/create", json={"type":"random"})
            if r.status_code == 200:
                d = (r.json() or {}).get("data") or {}
                email = str(d.get("email",""))
                if "@" in email:
                    client.post("https://22.do/action/mailbox/login", json={"email":email,"language":"en-US"})
                    tr = client.post("https://22.do/action/mailbox/applyToken",
                                     json={"email":email,"uuid":uuid.uuid4().hex.replace("-","")})
                    token = ((tr.json() or {}).get("data") or {}).get("token","")
                    log.info("22.do 箱: %s", email)
                    break
        except Exception as e:
            log.warning("22.do 异常: %s", str(e)[:50])
            await asyncio.sleep(15)
    if not email or not token:
        log.warning("22.do 建箱失败")
        return False

    # 求解 turnstile
    captcha = None
    for _ in range(3):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as c:
                r = await c.get(f"{CF_SOLVER}/turnstile",
                    params={"url":"https://nanobanana-pro.com/zh","sitekey":"0x4AAAAAACBMF7NSqVf-BSmE","proxy":kk})
                if r.status_code != 202: await asyncio.sleep(10); continue
                tid = r.json()["task_id"]
                dl = time.monotonic() + 90
                while time.monotonic() < dl:
                    rr = await c.get(f"{CF_SOLVER}/result", params={"id": tid})
                    if rr.status_code == 200: captcha = rr.json().get("value"); break
                    if rr.status_code in (404,408,422): break
                    await asyncio.sleep(2)
            if captcha and captcha != "captcha_fail": break
        except Exception as e:
            log.warning("求解异常: %s", str(e)[:50])
            await asyncio.sleep(15)
    if not captcha or captcha == "captcha_fail": log.warning("求解失败"); return False

    BTC = {"User-Agent":"Mozilla/5.0 Chrome/150","Content-Type":"application/json",
           "Origin":"https://nanobanana-pro.com","Referer":"https://nanobanana-pro.com/zh"}
    password = "Tf@" + str(int(time.time()))
    try:
        r = httpx.post("https://nanobanana-pro.com/api/auth/sign-up/email",
            headers={**BTC,"x-turnstile-token":captcha},
            json={"email":email,"password":password,"name":"TfUser","callbackURL":"/zh"}, proxy=kk, timeout=30)
        if r.status_code != 200: log.warning("sign-up: %s", r.text[:80]); return False
        log.info("sign-up 200")
    except Exception as e: log.warning("sign-up 异常: %s", str(e)[:50]); return False

    # 等 verify 邮件（22.do 确认能收到）
    got = None
    for i in range(300):
        try:
            mr = client.post("https://22.do/action/mailbox/message", json={"email":email,"lastime":0},
                             headers={"Authorization":"Bearer "+token})
            if mr.status_code == 200:
                msgs = (mr.json() or {}).get("data") or []
                for m in msgs:
                    if "Verify" in json.dumps(m.get("subject","")):
                        got = m; break
        except Exception:
            pass
        if got: log.info("verify 邮件到达 (%.1fmin)", i*2/60); break
        if i % 30 == 0 and i > 0: log.info("轮询中... %ds", i*2)
        await asyncio.sleep(2)
    if not got:
        log.warning("verify 未到，尝试直接登录")
        try:
            login = httpx.post("https://nanobanana-pro.com/api/auth/sign-in/email", headers=BTC,
                json={"email":email,"password":password,"callbackURL":"/zh"}, proxy=kk, timeout=30)
            if login.status_code == 200:
                ck = ";".join(f"{k}={v}" for k,v in login.cookies.items())
                if "__Secure-better-auth.session_token" in ck:
                    log.info("未验证登录成功！"); _add(email, ck, password); return True
        except Exception:
            pass
        return False

    # 取 verify 链接：从 inbox 网页 HTML 提取
    mid = str(got.get("id") or got.get("_id") or got.get("messageId") or "")
    link = None
    # 22.do inbox 页面渲染完整邮件内容，从中提取 verify 链接
    for path in ("/inbox", "/mailbox"):
        try:
            pg = client.get("https://22.do"+path)
            if pg.status_code == 200 and mid and mid in pg.text:
                m = re.search(r"https://[^\s\"'<>]+/api/auth/verify-email\?token=[^&\s\"'<>]+", pg.text)
                if m: link = m.group(0).replace("&amp;","&"); break
        except Exception:
            continue
    if not link:
        log.warning("22.do 无 verify 链接"); return False
    log.info("verify 链接: %s...", link[:50])

    try:
        v = httpx.get(link, headers={"User-Agent":"Mozilla/5.0"}, proxy=kk, timeout=20, follow_redirects=False)
        log.info("点链接: %s", v.status_code)
    except Exception as e: log.warning("点链接异常: %s", str(e)[:50])
    try:
        login = httpx.post("https://nanobanana-pro.com/api/auth/sign-in/email", headers=BTC,
            json={"email":email,"password":password,"callbackURL":"/zh"}, proxy=kk, timeout=30)
        if login.status_code != 200: log.warning("登录失败: %s", login.text[:80]); return False
        ck = ";".join(f"{k}={v}" for k,v in login.cookies.items())
        if "__Secure-better-auth.session_token" not in ck: log.warning("无 session"); return False
    except Exception as e: log.warning("登录异常: %s", str(e)[:50]); return False
    _add(email, ck, password)
    return True


async def main():
    log.info("nanobanana 号池自动注册循环启动，目标 %d，DB=%s", TARGET, DB)
    rnd = 0
    while True:
        ok = _ok_count()
        if ok >= TARGET: log.info("已达目标 %d 号", TARGET); break
        rnd += 1
        log.info("=== 第 %d 轮 当前号池: %d/%d ===", rnd, ok, TARGET)
        try:
            ok2 = await register_one()
            log.info("本轮: %s", "成功" if ok2 else "失败")
        except Exception as e:
            log.exception("异常: %s", e)
        await asyncio.sleep(30 if ok2 else 60)


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
    asyncio.run(main())