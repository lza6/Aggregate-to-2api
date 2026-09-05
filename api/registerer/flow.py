"""nanobanana 注册主流程（P0-5 从 registerer.py 拆出）。

向后兼容：`api.registerer` 旧路径仍 re-export 全部符号。
"""

from __future__ import annotations

import json
import logging
import sys

import httpx

from .. import (  # noqa: F401  (turnstile_client re-export 供测试 monkeypatch `api.turnstile_client.solve_turnstile`)
    config,
    turnstile_client,
)
from ..email_pool import email_pool
from ..providers.nanobanana import ACTION_CLAIM_DAILY_CHECKIN
from ..solver_guard import solver_guard
from .types import (
    RegistrationError,
    RegistrationErrorCategory,
    RegistrationSession,
    RegistrationStage,
    _parse_iso_ts,
    adaptive_backoff,
)
from .utils import (
    _browser_headers,
    _extract_verify_link,
    _gen_password,
    _mail_ai_extract_enabled,
    _proxy_host,
    _session_data_from_cookies,
    _th,
)

log = logging.getLogger("registerer")


def _mock_register() -> bool:
    """运行时读取包命名空间 `api.registerer.MOCK_REGISTER`。

    测试用 `monkeypatch.setattr("api.registerer.MOCK_REGISTER", ...)` 按名字换包属性；
    若 flow.py 在 import 时静态绑定 `from .types import MOCK_REGISTER`，patch 不会命中
    （原版单文件中二者同模块故天然生效）。此处运行时解析，保持旧 patch 契约。
    """
    return bool(getattr(sys.modules[__package__], "MOCK_REGISTER", False))


# ── nanobanana 自适应注册器 ─────────────────────────
class NanobananaRegisterer:
    """nanobanana 账号注册器：支持自适应故障分类、代理隔离与断点状态推进。"""

    provider = "nanobanana"
    base = "https://nanobanana-pro.com"
    SITEKEY = "0x4AAAAAACBMF7NSqVf-BSmE"
    turnstile_page = "https://nanobanana-pro.com/zh"

    def __init__(self) -> None:
        self.proxy: str | None = None
        self._current_proxy: str | None = config.PROXY
        self.client = httpx.Client(
            proxy=config.PROXY,
            timeout=httpx.Timeout(60.0),
            headers={"User-Agent": config.USER_AGENT},
        )
        self.last_session: RegistrationSession | None = None
        # v6.5.0: 最近注册会话语义快照（stage + 耗时），供前端号池「注册阶段/耗时」渲染
        self.live_session_snapshot: dict | None = None

    @staticmethod
    def _claim_response_ok(r: httpx.Response) -> bool:
        """解析签到 Server Action 响应，判断是否领取成功（0: 行含 success / rewardAmount）。"""
        for line in (r.text or "").splitlines():
            line = line.strip()
            if not line.startswith("0:"):
                continue
            try:
                resp = json.loads(line[2:].strip().replace("$$", "$"))
                if resp.get("success") or resp.get("data", {}).get("rewardAmount") is not None:
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def parse_claim_profile(r: httpx.Response) -> dict:
        """v6.3.4: 从签到 claim 响应提取完整画像（rewardAmount/cycleDay/nextClaimAt）。

        抓包确认响应形如（RSC 0: 行，JSON 内 data 字段）：
        {"success":true,"data":{"rewardAmount":3,"cycleDay":2,"nextDay":3,
          "nextClaimAt":"2026-08-29T07:00:00.000Z","currentPeriod":"daily-checkin:..."}}
        解析失败返回空 dict（调用方按 0 值兜底，不阻塞签到主流程）。
        """
        out: dict = {}
        for line in (r.text or "").splitlines():
            line = line.strip()
            if not line.startswith("0:"):
                continue
            try:
                resp = json.loads(line[2:].strip().replace("$$", "$"))
            except Exception:
                continue
            data = resp.get("data") or {}
            if not isinstance(data, dict):
                continue
            if data.get("rewardAmount") is not None:
                out["reward"] = int(data.get("rewardAmount") or 0)
            if data.get("cycleDay") is not None:
                out["cycle_day"] = int(data.get("cycleDay") or 0)
            if data.get("nextClaimAt"):
                out["next_claim_at"] = _parse_iso_ts(data.get("nextClaimAt"))
            if out:
                break
        return out

    def _ensure_client(self, email: str = "", force_rotate: bool = False) -> None:
        if force_rotate:
            want = config.PROXY
        else:
            want = self.proxy or config.PROXY
        # 空串代理（如环境变量 IF_PROXY="" 解析成 ""）会让 httpx 抛
        # "Unknown scheme for proxy URL URL('')"——统一归一化为 None（直连）
        if isinstance(want, str) and not want.strip():
            want = None

        if self._current_proxy != want or force_rotate:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = httpx.Client(
                proxy=want,
                timeout=httpx.Timeout(60.0),
                headers={"User-Agent": config.USER_AGENT},
            )
            self._current_proxy = want

    async def register_one(self) -> dict | None:
        """执行 nanobanana 注册流程：邮箱注册 -> 验证链接/直接登录 -> 拿 session cookie。"""
        session = RegistrationSession(provider=self.provider)
        self.last_session = session

        if _mock_register():
            import random
            import time

            email = f"mocknb{int(time.time())}{random.randint(0, 999)}@mock.com"
            session.advance_to(RegistrationStage.COMPLETED, email=email, credits=4)
            adaptive_backoff.record_success(self.provider)
            self.live_session_snapshot = session.snapshot()
            return {
                "email": email,
                "cookie": "mock-session",
                "password": "mock123",
                "credits": 4,
                "session_id": session.session_id,
                "register_ip": "",
            }

        try:
            # 阶段 1: 邮箱分配
            try:
                email, src = await email_pool.allocate(self.provider)
                src_name = (
                    (src or {}).get("source", "unknown") if isinstance(src, dict) else getattr(src, "name", "unknown")
                )
                session.advance_to(
                    RegistrationStage.EMAIL_ALLOCATED,
                    email=email,
                    email_source=src_name,
                    email_state=src if isinstance(src, dict) else {},
                )
            except Exception as e:
                err_str = str(e)
                cat = (
                    RegistrationErrorCategory.EMAIL_RATE_LIMITED
                    if "429" in err_str or "限流" in err_str
                    else RegistrationErrorCategory.TRANSIENT
                )
                raise RegistrationError(
                    f"邮箱池分配失败: {e}", category=cat, stage=RegistrationStage.INIT, provider=self.provider
                )

            self._ensure_client(email)
            session.proxy_used = self._current_proxy or "direct"
            password = _gen_password()
            session.password = password

            # 阶段 2: Turnstile 求解
            try:
                captcha, _ = await turnstile_client.solve_turnstile(
                    config.CF_SOLVER_URL,
                    self.turnstile_page,
                    self.SITEKEY,
                    config.TURNSTILE_TIMEOUT,
                    proxy=config.PROXY,
                )
                session.advance_to(RegistrationStage.CAPTCHA_SOLVED, captcha_token=captcha)
            except Exception as e:
                solver_guard.record_failure("cf_solver_failed")
                raise RegistrationError(
                    f"Turnstile 求解失败: {e}",
                    category=RegistrationErrorCategory.CF_BLOCKED,
                    stage=RegistrationStage.EMAIL_ALLOCATED,
                    provider=self.provider,
                )

            # 阶段 3: 发起 sign-up 注册
            try:
                r = await _th(
                    self.client.post,
                    f"{self.base}/api/auth/sign-up/email",
                    headers={
                        **_browser_headers(self.base, f"{self.base}/zh"),
                        "x-turnstile-token": captcha,
                    },
                    json={"email": email, "password": password, "name": "TfUser", "callbackURL": "/zh"},
                )
            except Exception as e:
                raise RegistrationError(
                    f"注册请求异常: {e}",
                    category=RegistrationErrorCategory.TRANSIENT,
                    stage=RegistrationStage.CAPTCHA_SOLVED,
                    provider=self.provider,
                )

            if r.status_code == 403:
                self._ensure_client(email, force_rotate=True)
                raise RegistrationError(
                    "sign-up 触发 403 风控",
                    category=RegistrationErrorCategory.IP_BLOCKED,
                    stage=RegistrationStage.CAPTCHA_SOLVED,
                    provider=self.provider,
                )
            if r.status_code == 429:
                raise RegistrationError(
                    "sign-up 触发 429 限流",
                    category=RegistrationErrorCategory.EMAIL_RATE_LIMITED,
                    stage=RegistrationStage.CAPTCHA_SOLVED,
                    provider=self.provider,
                )
            if r.status_code != 200:
                await email_pool.record(email, self.provider, "error", "signup_fail")
                resp_text = str(r.text)[:150]
                # INVALID_EMAIL → 域名已被上游拉黑，记入 domain_risk，下次分配跳过该域名
                if "invalid_email" in resp_text.lower() or "invalid email" in resp_text.lower():
                    cat = RegistrationErrorCategory.EMAIL_RATE_LIMITED
                elif "turnstile" in resp_text.lower() or "captcha" in resp_text.lower():
                    cat = RegistrationErrorCategory.CF_BLOCKED
                else:
                    cat = (
                        RegistrationErrorCategory.IP_BLOCKED
                        if r.status_code in (401, 403)
                        else RegistrationErrorCategory.TRANSIENT
                    )
                raise RegistrationError(
                    f"sign-up 失败 HTTP {r.status_code}: {resp_text}",
                    category=cat,
                    stage=RegistrationStage.CAPTCHA_SOLVED,
                    provider=self.provider,
                )

            session.advance_to(RegistrationStage.VERIFICATION_SENT)

            # 阶段 4: 收取验证链接（如超时仍允许尝试直接登录）
            mail = await email_pool.wait_for_mail(email, session.email_state, 90.0, "Verify")
            link = _extract_verify_link(mail)
            if not link and _mail_ai_extract_enabled():
                # AI 兜底：正则未命中时尝试 LLM 提取（默认关闭，失败返回 None 不阻塞）
                from ..mail_extract import extract_verify_link as _ai_extract_link

                link = await _ai_extract_link(mail, ai=True)
            if not link:
                log.info("nanobanana %s 未收到验证链接，尝试直接登录", email)
            else:
                session.advance_to(RegistrationStage.CODE_OR_LINK_RECEIVED, verify_link=link)
                try:
                    await _th(self.client.get, link, headers={"User-Agent": config.USER_AGENT})
                except Exception as e:
                    log.warning("nanobanana 验证链接访问异常 %s: %s", email, e)

            # 阶段 5: 登录求解与获取 Session Cookie
            try:
                login_captcha, _ = await turnstile_client.solve_turnstile(
                    config.CF_SOLVER_URL,
                    self.turnstile_page,
                    self.SITEKEY,
                    config.TURNSTILE_TIMEOUT,
                    proxy=config.PROXY,
                )
            except Exception as e:
                log.warning("nanobanana 登录 Turnstile 求解失败: %s", e)
                login_captcha = ""

            try:
                login = await _th(
                    self.client.post,
                    f"{self.base}/api/auth/sign-in/email",
                    headers={
                        **_browser_headers(self.base, f"{self.base}/zh"),
                        "x-turnstile-token": login_captcha,
                    },
                    json={"email": email, "password": password, "callbackURL": "/zh"},
                )
            except Exception as e:
                raise RegistrationError(
                    f"sign-in 请求网络异常: {e}",
                    category=RegistrationErrorCategory.TRANSIENT,
                    stage=RegistrationStage.CODE_OR_LINK_RECEIVED,
                    provider=self.provider,
                )

            # 从 client jar 提取累积的全部 cookies（含重定向/其它响应累积的 __Secure-better-auth.session_data 等），
            # 而非仅 login 响应 cookies。
            cookie = "; ".join(f"{k}={v}" for k, v in self.client.cookies.items())
            if login.status_code == 400 or "__Secure-better-auth.session_token" not in self.client.cookies:
                await email_pool.record(email, self.provider, "error", "login_fail")
                if login.status_code == 403:
                    self._ensure_client(email, force_rotate=True)
                    cat = RegistrationErrorCategory.IP_BLOCKED
                elif login.status_code == 429:
                    cat = RegistrationErrorCategory.EMAIL_RATE_LIMITED
                else:
                    cat = RegistrationErrorCategory.TRANSIENT
                raise RegistrationError(
                    f"登录失败 HTTP {login.status_code}: {str(login.text)[:120]}",
                    category=cat,
                    stage=RegistrationStage.CODE_OR_LINK_RECEIVED,
                    provider=self.provider,
                )

            session.advance_to(RegistrationStage.LOGGED_IN, session_cookie=cookie, credits=4)
            session_data = _session_data_from_cookies(self.client.cookies)
            await email_pool.record(email, self.provider, "ok", note="no_verify" if not link else "verified")
            adaptive_backoff.record_success(self.provider)
            session.advance_to(RegistrationStage.COMPLETED)
            log.info(
                "nanobanana 注册成功 %s credits=4 (session: %s, has_session_data=%s)",
                email,
                session.session_id,
                bool(session_data),
            )
            self.live_session_snapshot = session.snapshot()

            return {
                "email": email,
                "cookie": cookie,
                "session_data": session_data,
                "password": password,
                "credits": 4,
                "session_id": session.session_id,
                "register_ip": _proxy_host(session.proxy_used),
            }

        except RegistrationError as err:
            session.mark_failed(err.message, err.category)
            backoff_sec = adaptive_backoff.compute_backoff(self.provider, err.category)
            log.warning(
                "nanobanana 注册在阶段 [%s] 发生故障 [%s]: %s (退避 %.1fs)",
                err.stage.value,
                err.category.value,
                err.message,
                backoff_sec,
            )
            self.live_session_snapshot = session.snapshot()
            return None
        except Exception as err:
            session.mark_failed(str(err), RegistrationErrorCategory.TRANSIENT)
            backoff_sec = adaptive_backoff.compute_backoff(self.provider, RegistrationErrorCategory.TRANSIENT)
            log.warning("nanobanana 发生未捕获异常退避 %.1fs: %s", backoff_sec, err)
            self.live_session_snapshot = session.snapshot()
            return None

    async def checkin(self, acc: dict) -> int | None:
        """每日签到（Next.js Server Action claimDailyCheckinAction），返回新余额。

        协议级路径（与注册一致，用户已用真实浏览器验证可行）：
        1. 先用 cf 求解 + /api/auth/sign-in/email 重新登录，拿【新鲜】better-auth 会话
           （会话绑定本次出口 IP，不再依赖可能失效/异 IP 的旧 cookie）
        2. 用新会话查 daily-checkin/status
        3. 若需 captcha 则同一出口解 turnstile
        4. 调 claimDailyCheckinAction 领取
        关键：登录与签到必须用同一出口（config.PROXY 或直连），否则会话 IP 不匹配被拒。
        """
        if _mock_register():
            return int(acc.get("credits", 0)) + 4
        email = acc.get("email")
        password = acc.get("password")
        # 出口统一：直连/服务器出口（config.PROXY 已空 → 直连），与会话绑定 IP 一致
        self._ensure_client(email)
        try:
            # 步骤 0：重新登录拿新鲜会话（cf 求解 + sign-in 端点）
            fresh = await self.re_login(email, password) if password else None
            if fresh and fresh.get("cookie"):
                cookie = fresh["cookie"]
            else:
                # 退路：沿用旧 cookie（但大概率因 IP/过期被拒，仅作最后尝试）
                cookie = acc.get("cookie")
            if not cookie:
                return None

            # 步骤 1：查状态
            st = await _th(
                self.client.get,
                f"{self.base}/api/credits/daily-checkin/status",
                headers={"Cookie": cookie, "User-Agent": config.USER_AGENT},
            )
            data = (st.json() or {}).get("data") or {}
            if data.get("hasClaimedToday"):
                # 已签状态也回传统一画像 dict（当前周期天从 status 响应取 currentCycleDay），
                # 让 account_pool 落库 checkin_total/credits 画像，而非只回 int 导致统计缺失
                bal = await _th(
                    self.client.get,
                    f"{self.base}/api/credits/balance",
                    headers={"Cookie": cookie, "User-Agent": config.USER_AGENT},
                )
                profile = {
                    "credits": int((bal.json() or {}).get("credits", 0)),
                    "cycle_day": int(data.get("currentCycleDay") or 0),
                    "reward": 0,  # 今天已领过，无新增
                    # 下次签到时间从 status.nextClaimAt 提取（美区时区重置点）
                    "next_claim_at": _parse_iso_ts(data.get("nextClaimAt")),
                }
                return profile

            # 步骤 2：Server Action 领取（需要 captcha 则同一出口解）
            body = [{"captchaToken": ""}]
            if data.get("requiresCaptcha"):
                try:
                    captcha, _ = await turnstile_client.solve_turnstile(
                        config.CF_SOLVER_URL,
                        self.turnstile_page,
                        self.SITEKEY,
                        config.TURNSTILE_TIMEOUT,
                        proxy=config.PROXY,  # 同一出口，与登录一致
                    )
                    body = [{"captchaToken": captcha}]
                except Exception:
                    return None

            payload = json.dumps(body).replace("$", "$$") if "$" in json.dumps(body) else json.dumps(body)
            from ..providers.action_sniffer import action_sniffer, is_stale_action_response

            claim_action = await action_sniffer.get_action_id("claim_daily_checkin")
            r = await _th(
                self.client.post,
                f"{self.base}/zh",
                headers={
                    "Cookie": cookie,
                    "User-Agent": config.USER_AGENT,
                    "Next-Action": claim_action or ACTION_CLAIM_DAILY_CHECKIN,
                    "Accept": "text/x-component",
                    "Content-Type": "text/plain;charset=UTF-8",
                },
                content=payload,
            )

            claimed = self._claim_response_ok(r)
            if not claimed and is_stale_action_response(r):
                # ISSUE-03: 404 / Action 不匹配 → force_refresh 嗅探自愈，用新 ID 重试一次
                fresh = await action_sniffer.get_action_id("claim_daily_checkin", force_refresh=True)
                if fresh and fresh != claim_action:
                    log.warning("nanobanana 签到 Action 失效，嗅探到新 ID %s...，自愈重试", fresh[:12])
                    r = await _th(
                        self.client.post,
                        f"{self.base}/zh",
                        headers={
                            "Cookie": cookie,
                            "User-Agent": config.USER_AGENT,
                            "Next-Action": fresh,
                            "Accept": "text/x-component",
                            "Content-Type": "text/plain;charset=UTF-8",
                        },
                        content=payload,
                    )
                    claimed = self._claim_response_ok(r)
            if not claimed:
                log.warning("nanobanana 签到领取响应异常: %s", (r.text or "")[:120])
                return None

            bal = await _th(
                self.client.get,
                f"{self.base}/api/credits/balance",
                headers={"Cookie": cookie, "User-Agent": config.USER_AGENT},
            )
            # v6.3.4: 签到画像随余额一起返回，供 account_pool 落库累计签到/周期天数
            profile = self.parse_claim_profile(r)
            profile["credits"] = int((bal.json() or {}).get("credits", 0))
            return profile
        except Exception as e:
            log.warning("nanobanana 签到失败 %s: %s", acc.get("email", "?"), e)
        return None

    async def re_login(self, email: str, password: str) -> dict | None:
        """cookie 失效后重新登录（Turnstile 求解 + sign-in 端点），返回新会话 cookie。

        复用 register_one 的登录流程：代理修复 + Turnstile 求解 + POST /api/auth/sign-in/email，
        从 client cookie jar 汇总 __Secure-better-auth 会话 cookie，并顺带取 session_data。
        """
        if _mock_register():
            return {"email": email, "password": password, "cookie": "mock-session", "session_data": ""}
        # 沿用 checkin 的出口代理（也可为空直连）；邻代码每次操作都保证代理新鲜
        self._ensure_client(email)
        try:
            login_captcha = ""
            try:
                login_captcha, _ = await turnstile_client.solve_turnstile(
                    config.CF_SOLVER_URL,
                    self.turnstile_page,
                    self.SITEKEY,
                    config.TURNSTILE_TIMEOUT,
                    proxy=config.PROXY,
                )
            except Exception as e:
                solver_guard.record_failure("cf_solver_failed")
                log.warning("nanobanana re_login Turnstile 求解失败: %s", e)

            login = await _th(
                self.client.post,
                f"{self.base}/api/auth/sign-in/email",
                headers={
                    **_browser_headers(self.base, f"{self.base}/zh"),
                    "x-turnstile-token": login_captcha,
                },
                json={"email": email, "password": password, "callbackURL": "/zh"},
            )

            cookie = "; ".join(f"{k}={v}" for k, v in self.client.cookies.items())
            if (
                login.status_code == 400
                or "__Secure-better-auth.session_token" not in self.client.cookies
                or not cookie
            ):
                log.warning("nanobanana re_login 失败 %s: HTTP %s（无 session_token）", email, login.status_code)
                return None

            session_data = _session_data_from_cookies(self.client.cookies)
            log.info("nanobanana re_login 成功 %s (has_session_data=%s)", email, bool(session_data))
            return {
                "email": email,
                "password": password,
                "cookie": cookie,
                "session_data": session_data,
            }
        except Exception as e:
            log.warning("nanobanana re_login 异常 %s: %s", email, e)
        return None


# ── 注册器注册表 ─────────────────────────────────
def build_registerers() -> dict[str, object]:
    out: dict[str, object] = {}
    out["nanobanana"] = NanobananaRegisterer()
    return out


__all__ = [
    "NanobananaRegisterer",
    "build_registerers",
]
