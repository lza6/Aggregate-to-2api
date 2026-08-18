"""自动注册器：minimaxh3 / nanobanana 账号注册 + nanobanana 每日签到。

注册闭环复用邮箱池（temp.tf 无敌十几亿）+ cf_solver Turnstile 求解。
支持 MOCK 模式（IF_MOCK_REGISTER=1）：不真实调用上游，返回假账号用于 E2E/测试。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import httpx

from . import config
from . import turnstile_client
from .email_pool import email_pool

log = logging.getLogger("registerer")

MOCK_REGISTER = config.MOCK_REGISTER


def _browser_headers(origin: str, referer: str | None = None) -> dict:
    return {
        "User-Agent": config.USER_AGENT,
        "Accept": "*/*", "Content-Type": "application/json",
        "Origin": origin, "Referer": referer or (origin + "/"),
    }


async def _th(fn, *a, **k):
    """H1(审计修复)：注册流程的同步 httpx.Client 调用丢进线程池，避免阻塞事件循环。

    to_thread 每次起一个线程执行单个调用（await 串行），httpx 同步 Client 线程安全，无并发风险。
    """
    return await asyncio.to_thread(fn, *a, **k)


# ── minimaxh3 注册 ────────────────────────────────
class Minimaxh3Registerer:
    provider = "minimaxh3"
    base = "https://minimaxh3.ai"
    # turnstile 挂在中文注册页 /zh；cf_solver 必须用该页面求解，token 才被站点校验通过
    turnstile_page = "https://minimaxh3.ai/zh"
    # minimaxh3 自己的 Turnstile sitekey（逆向自前端 JS e0e4cc9a2a71a40b.js，勿用 config.SITEKEY=imagefree 的）
    SITEKEY = "0x4AAAAAADwZ49KghcP-p2lE"

    def __init__(self) -> None:
        self.proxy: str | None = None      # 当前注册出口代理（批量注册时由代理池轮换注入）
        self._current_proxy: str | None = config.PROXY
        self.client = httpx.Client(proxy=config.PROXY, timeout=httpx.Timeout(60.0),
                                   headers={"User-Agent": config.USER_AGENT})

    def _ensure_client(self) -> None:
        """注册代理变化时重建 client（每号一代理，防批量注册同 IP 风控）。"""
        want = self.proxy or config.PROXY
        if self._current_proxy != want:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = httpx.Client(proxy=want, timeout=httpx.Timeout(60.0),
                                       headers={"User-Agent": config.USER_AGENT})
            self._current_proxy = want

    async def register_one(self) -> dict | None:
        """注册 1 个 minimaxh3 账号，返回 {email, cookie, password, credits}。

        流程：邮箱 → turnstile captchaToken → send-verification → 邮箱收 6 位码 →
        csrf → callback/email-code 换 session cookie → 确认 4 积分。
        """
        self._ensure_client()
        if MOCK_REGISTER:
            import random
            email = f"mock{int(time.time())}{random.randint(0,999)}@mock.com"
            return {"email": email, "cookie": "mock-session", "password": "mock123",
                    "credits": 4}
        email, src = email_pool.allocate(self.provider, prefer_domain="high.edu.pl")
        # 1) 求解 turnstile（captchaToken；用 minimaxh3 自己的 sitekey + 注册页 /zh）
        try:
            captcha = await turnstile_client.solve_turnstile(
                config.CF_SOLVER_URL, self.turnstile_page, self.SITEKEY, config.TURNSTILE_TIMEOUT)
        except Exception as e:
            log.warning("minimaxh3 注册求解失败: %s", e)
            return None
        # 2) send-verification
        r = await _th(self.client.post, f"{self.base}/api/auth/send-verification",
                      headers=_browser_headers(self.base, f"{self.base}/zh"),
                      json={"email": email, "locale": "zh", "captchaToken": captcha})
        data = r.json()
        token = data.get("token")
        if not token:
            log.warning("minimaxh3 send-verification 失败: %s", str(data)[:150])
            return None
        # 3) 邮箱收 6 位码
        mail = await asyncio.to_thread(email_pool.wait_for_mail, email, src, 120.0, "验证码")
        code = _extract_code(mail)
        if not code:
            log.warning("minimaxh3 未收到验证码: %s", email)
            email_pool.record(email, self.provider, "error", "no_code")
            return None
        # 4) csrf + callback/email-code
        csrf_r = await _th(self.client.get, f"{self.base}/api/auth/csrf",
                           headers=_browser_headers(self.base))
        csrf = (csrf_r.json() or {}).get("csrfToken", "")
        cb = await _th(self.client.post,
                       f"{self.base}/api/auth/callback/email-code?",
                       headers={"User-Agent": config.USER_AGENT, "Content-Type": "application/x-www-form-urlencoded",
                                "Origin": self.base, "Referer": f"{self.base}/zh"},
                       data={"token": token, "code": code, "redirect": "false", "csrfToken": csrf,
                             "callbackUrl": "https%3A%2F%2Fminimaxh3.ai%2Fzh"},
                       )
        cookie = "; ".join(f"{k}={v}" for k, v in cb.cookies.items())
        if "__Secure-authjs.session-token" not in cb.cookies:
            log.warning("minimaxh3 登录失败: %s", str(cb.text)[:150])
            email_pool.record(email, self.provider, "error", "login_fail")
            return None
        # 5) 确认积分
        credits = 0
        try:
            c = await _th(self.client.get, f"{self.base}/api/get-user-credits",
                          headers={"Cookie": cookie, "User-Agent": config.USER_AGENT})
            credits = int(((c.json() or {}).get("data") or {}).get("credits", 0))
        except Exception:
            pass
        email_pool.record(email, self.provider, "ok", f"credits={credits}")
        log.info("minimaxh3 注册成功 %s credits=%d", email, credits)
        return {"email": email, "cookie": cookie, "password": "", "credits": credits}

    async def checkin(self, acc: dict) -> int | None:
        return None  # minimaxh3 无签到


def _extract_code(mail: dict | None) -> str | None:
    """从验证码邮件提取 6 位数字。"""
    if not mail:
        return None
    import re
    blob = str(mail.get("bodyPreview") or "") + str(mail.get("bodyHtml") or "") + str(mail.get("subject") or "")
    m = re.search(r"\b(\d{6})\b", blob)
    return m.group(1) if m else None


# ── nanobanana 注册 + 签到 ────────────────────────
class NanobananaRegisterer:
    provider = "nanobanana"
    base = "https://nanobanana-pro.com"
    # nanobanana 自己的 Turnstile sitekey（逆向自注册抓包，勿用 aifreeforever 的）
    SITEKEY = "0x4AAAAAACBMF7NSqVf-BSmE"
    # turnstile 挂在中文页 /zh；用该页面求解 token 才被校验通过
    turnstile_page = "https://nanobanana-pro.com/zh"

    def __init__(self) -> None:
        self.proxy: str | None = None
        self._current_proxy: str | None = config.PROXY
        self.client = httpx.Client(proxy=config.PROXY, timeout=httpx.Timeout(60.0),
                                   headers={"User-Agent": config.USER_AGENT})

    def _ensure_client(self) -> None:
        want = self.proxy or config.PROXY
        if self._current_proxy != want:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = httpx.Client(proxy=want, timeout=httpx.Timeout(60.0),
                                       headers={"User-Agent": config.USER_AGENT})
            self._current_proxy = want

    async def register_one(self) -> dict | None:
        """注册 1 个 nanobanana 账号：邮箱注册 → 验证链接点击 → 登录 → 4 积分。"""
        self._ensure_client()
        if MOCK_REGISTER:
            import random
            email = f"mocknb{int(time.time())}{random.randint(0,999)}@mock.com"
            return {"email": email, "cookie": "mock-session", "password": "mock123", "credits": 4}
        email, src = email_pool.allocate(self.provider, prefer_domain="high.edu.pl")
        password = f"Tf@{int(time.time())}"
        # 1) turnstile + sign-up（用 nanobanana 自己的 sitekey + 注册页 /zh）
        try:
            captcha = await turnstile_client.solve_turnstile(
                config.CF_SOLVER_URL, self.turnstile_page, self.SITEKEY, config.TURNSTILE_TIMEOUT)
        except Exception as e:
            log.warning("nanobanana 注册求解失败: %s", e)
            return None
        r = await _th(self.client.post, f"{self.base}/api/auth/sign-up/email",
                      headers={**_browser_headers(self.base, f"{self.base}/zh"),
                               "x-turnstile-token": captcha},
                      json={"email": email, "password": password, "name": "TfUser",
                            "callbackURL": "/zh"})
        if r.status_code != 200:
            log.warning("nanobanana 注册失败: %s", str(r.text)[:150])
            email_pool.record(email, self.provider, "error", "signup_fail")
            return None
        # 2) 邮箱收验证链接
        mail = await asyncio.to_thread(email_pool.wait_for_mail, email, src, 120.0, "Verify")
        link = _extract_verify_link(mail)
        if not link:
            email_pool.record(email, self.provider, "error", "no_verify_link")
            return None
        # 3) 点验证链接
        try:
            await _th(self.client.get, link, headers={"User-Agent": config.USER_AGENT})
        except Exception as e:
            log.warning("nanobanana 验证链接失败 %s: %s", email, e)
        # 4) 登录拿 session cookie
        login = await _th(self.client.post, f"{self.base}/api/auth/sign-in/email",
                          headers=_browser_headers(self.base, f"{self.base}/zh"),
                          json={"email": email, "password": password, "callbackURL": "/zh"})
        cookie = "; ".join(f"{k}={v}" for k, v in login.cookies.items())
        if "__Secure-better-auth.session_token" not in login.cookies:
            email_pool.record(email, self.provider, "error", "login_fail")
            return None
        email_pool.record(email, self.provider, "ok")
        return {"email": email, "cookie": cookie, "password": password, "credits": 4}

    async def checkin(self, acc: dict) -> int | None:
        """每日签到（Next.js Server Action claimDailyCheckinAction），返回新余额。"""
        if MOCK_REGISTER:
            return int(acc.get("credits", 0)) + 4
        self._ensure_client()  # L6(审计修复): 签到也用当前代理（脚本轮换过则用新 client）
        cookie = acc.get("cookie")
        if not cookie:
            return None
        try:
            # 1) 查状态：是否需要 captcha
            st = await _th(self.client.get, f"{self.base}/api/credits/daily-checkin/status",
                           headers={"Cookie": cookie, "User-Agent": config.USER_AGENT})
            data = (st.json() or {}).get("data") or {}
            if data.get("hasClaimedToday"):
                # 今日已签，直接查余额
                bal = await _th(self.client.get, f"{self.base}/api/credits/balance",
                                headers={"Cookie": cookie, "User-Agent": config.USER_AGENT})
                return int((bal.json() or {}).get("credits", 0))
            # 2) Server Action 领取（claimDailyCheckinAction）
            body = [{"captchaToken": ""}]
            if data.get("requiresCaptcha"):
                try:
                    captcha = await turnstile_client.solve_turnstile(
                        config.CF_SOLVER_URL, self.turnstile_page, self.SITEKEY,
                        config.TURNSTILE_TIMEOUT)
                    body = [{"captchaToken": captcha}]
                except Exception:
                    return None
            # L5(审计修复): body 只序列化一次（避免重复 json.dumps）
            payload = json.dumps(body).replace("$", "$$") if "$" in json.dumps(body) else json.dumps(body)
            r = await _th(self.client.post, f"{self.base}/zh",
                          headers={
                              "Cookie": cookie, "User-Agent": config.USER_AGENT,
                              "Next-Action": "7fa3d4d28767dbc090ad4228dff062a1e20d421ce2",
                              "Accept": "text/x-component",
                              "Content-Type": "text/plain;charset=UTF-8",
                          },
                          content=payload)
            # L1(审计修复): 校验领取响应（Server Action 0: 行应含 success；失败不误记签到成功）
            claimed = False
            for line in (r.text or "").splitlines():
                line = line.strip()
                if line.startswith("0:"):
                    try:
                        resp = json.loads(line[2:].strip().replace("$$", "$"))
                        if resp.get("success") or resp.get("data", {}).get("rewardAmount") is not None:
                            claimed = True
                    except Exception:
                        pass
            if not claimed:
                log.warning("nanobanana 签到领取响应异常: %s", (r.text or "")[:120])
                return None
            # 领取后查余额
            bal = await _th(self.client.get, f"{self.base}/api/credits/balance",
                            headers={"Cookie": cookie, "User-Agent": config.USER_AGENT})
            return int((bal.json() or {}).get("credits", 0))
        except Exception as e:
            log.warning("nanobanana 签到失败 %s: %s", acc.get("email", "?"), e)
        return None


def _extract_verify_link(mail: dict | None) -> str | None:
    """从验证邮件提取 verify-email 链接。"""
    if not mail:
        return None
    import re
    blob = str(mail.get("bodyHtml") or "") + str(mail.get("bodyPreview") or "")
    m = re.search(r'https://[^\s"\'<>]+/api/auth/verify-email\?token=[^&\s"\'<>]+', blob)
    return (m.group(0).replace("&amp;", "&") if m else None)


# ── 注册器注册表 ─────────────────────────────────
def build_registerers() -> dict[str, object]:
    out: dict[str, object] = {}
    out["minimaxh3"] = Minimaxh3Registerer()
    out["nanobanana"] = NanobananaRegisterer()
    return out
