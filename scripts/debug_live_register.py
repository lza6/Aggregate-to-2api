"""端到端现场单号注册+收信+激活+登录+入库+签到验证脚本。"""

import asyncio
import json
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("debug_register")

from api import config
from api import turnstile_client
from api.account_pool import account_pool
from api.email_pool import email_pool
from api.registerer import NanobananaRegisterer, _browser_headers, _extract_verify_link, _th


async def step_by_step_nanobanana():
    reg = NanobananaRegisterer()
    log.info("========== 1. 邮箱分配测试 ==========")
    # 尝试各邮箱源直到拿到可用邮箱
    email, src = None, None
    for sname in ["22.do", "linshi-email", "temp-mail"]:
        try:
            email, src = await email_pool.allocate("nanobanana", prefer_source=sname)
            log.info("成功从 [%s] 分配邮箱: %s", sname, email)
            break
        except Exception as e:
            log.warning("源 [%s] 分配失败: %s", sname, e)

    if not email:
        log.error("所有邮箱源均分配失败！")
        return False

    log.info("========== 2. 人机验证求解 ==========")
    captcha, dur = await turnstile_client.solve_turnstile(config.CF_SOLVER_URL, reg.turnstile_page, reg.SITEKEY, 60.0)
    log.info("求解成功 (耗时 %.1fs): %s...", dur, captcha[:30])

    log.info("========== 3. 发送注册请求 ==========")
    password = f"Tf@{int(time.time())}"
    r = await _th(
        reg.client.post,
        f"{reg.base}/api/auth/sign-up/email",
        headers={**_browser_headers(reg.base, f"{reg.base}/zh"), "x-turnstile-token": captcha},
        json={"email": email, "password": password, "name": "TfUser", "callbackURL": "/zh"},
    )
    log.info("注册响应 HTTP %s: %s", r.status_code, r.text[:200])
    if r.status_code != 200:
        log.error("注册请求失败，终止")
        return False

    log.info("========== 4. 等待验证邮件 (最长 180s) ==========")
    mail = None
    t0 = time.monotonic()
    while time.monotonic() - t0 < 180:
        # 直接拉取邮件列表并打印
        src_obj = next((s for s in email_pool._sources if s.name == src.get("source")), None)
        if src_obj:
            mails = await src_obj.fetch_mails(email, src)
            log.info("已等待 %.1fs，当前收件箱邮件数: %d", time.monotonic() - t0, len(mails))
            if mails:
                log.info("收到邮件数据: %s", json.dumps(mails, ensure_ascii=False)[:300])
                mail = mails[0]
                break
        await asyncio.sleep(5)

    if not mail:
        log.error("超时未收到验证邮件！")
        return False

    link = _extract_verify_link(mail)
    log.info("提取到的激活链接: %s", link)
    if not link:
        log.error("未能从邮件中解析出激活链接！")
        return False

    log.info("========== 5. 请求激活链接 ==========")
    r_act = await _th(reg.client.get, link, headers={"User-Agent": config.USER_AGENT})
    log.info("激活响应 HTTP %s", r_act.status_code)

    log.info("========== 6. 登录并换取 Session Cookie ==========")
    # 登录也求解一个 turnstile 防止拦截
    login_captcha, _ = await turnstile_client.solve_turnstile(
        config.CF_SOLVER_URL, reg.turnstile_page, reg.SITEKEY, 60.0
    )
    login = await _th(
        reg.client.post,
        f"{reg.base}/api/auth/sign-in/email",
        headers={**_browser_headers(reg.base, f"{reg.base}/zh"), "x-turnstile-token": login_captcha},
        json={"email": email, "password": password, "callbackURL": "/zh"},
    )
    log.info("登录响应 HTTP %s", login.status_code)
    log.info("登录 Cookies: %s", list(login.cookies.keys()))
    cookie = "; ".join(f"{k}={v}" for k, v in login.cookies.items())
    if "__Secure-better-auth.session_token" not in login.cookies:
        log.error("登录未获取到 Session Token！返回: %s", login.text[:200])
        return False

    log.info("========== 7. 写入号池数据库 ==========")
    account_pool.add("nanobanana", email, cookie, password=password, credits=4)
    log.info("✅ 账号成功入库！当前 nanobanana 账号数: %d", len(account_pool.get("nanobanana")))

    log.info("========== 8. 立即验证签到接口 ==========")
    bal = await reg.checkin({"email": email, "cookie": cookie, "password": password, "credits": 4})
    log.info("签到后余额: %s", bal)
    return True


if __name__ == "__main__":
    asyncio.run(step_by_step_nanobanana())
