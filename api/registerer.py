"""自动注册器与自适应注册工作流 (Adaptive Registration Worker)。

功能与架构特性：
1. 支持 nanobanana 账号自动化注册闭环与 nanobanana 每日签到。
2. 建立注册失败自适应分类退避模型 (Adaptive Error Backoff)：
   - CF_BLOCKED: CF 阻断 (Turnstile 求解失败/Cloudflare WAF 拦截) -> 快速退避 30s，并标记求解器状态。
   - EMAIL_RATE_LIMITED: 邮箱频控 (429 / 验证码收取超时 / 建箱限流) -> 退避 60s，并触发邮箱池切源。
   - IP_BLOCKED: IP 污染 / 提供商风控 (403 Forbidden / 注册被拒 / 频繁异常) -> 退避 120s，并强制轮换住宅代理/新 IP。
   - TRANSIENT: 其他瞬态错误 -> 指数退避 (2s, 4s, 8s, 最大 30s)。
3. 断点续跑与阶段状态机 (RegistrationStage & RegistrationSession)：
   - 记录 INIT -> EMAIL_ALLOCATED -> CAPTCHA_SOLVED -> VERIFICATION_SENT -> CODE_RECEIVED -> LOGGED_IN 状态流转。
   - 在各阶段记录上下文与临时凭据，避免异常后残留脏数据。
4. 支持 MOCK 模式（IF_MOCK_REGISTER=1）：用于无外部依赖的高速 CI/E2E 测试。
"""
from __future__ import annotations

import asyncio
import enum
import json
import logging
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from . import config
from . import turnstile_client
from .email_pool import email_pool
from .proxy_pool import proxy_pool
from .solver_guard import solver_guard
from .providers.nanobanana import ACTION_CLAIM_DAILY_CHECKIN

log = logging.getLogger("registerer")

MOCK_REGISTER = config.MOCK_REGISTER


class RegistrationStage(str, enum.Enum):
    """注册阶段状态枚举。"""
    INIT = "init"
    EMAIL_ALLOCATED = "email_allocated"
    CAPTCHA_SOLVED = "captcha_solved"
    VERIFICATION_SENT = "verification_sent"
    CODE_OR_LINK_RECEIVED = "code_or_link_received"
    LOGGED_IN = "logged_in"
    COMPLETED = "completed"
    FAILED = "failed"


class RegistrationErrorCategory(str, enum.Enum):
    """注册故障分类。"""
    CF_BLOCKED = "cf_blocked"            # CF 阻断 / Turnstile 求解失败 / WAF 拦截
    EMAIL_RATE_LIMITED = "email_rate_limited"  # 邮箱频控 (429 / 验证码收取超时 / 建箱限流)
    IP_BLOCKED = "ip_blocked"            # IP 污染 / 提供商风控 (403 Forbidden / 注册被拒)
    TRANSIENT = "transient"              # 其他瞬态网络错误 (连接抖动 / 超时 / 5xx)


class RegistrationError(Exception):
    """带故障分类与阶段状态的结构化注册异常。"""

    def __init__(
        self,
        message: str,
        category: RegistrationErrorCategory = RegistrationErrorCategory.TRANSIENT,
        stage: RegistrationStage = RegistrationStage.INIT,
        provider: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.category = category
        self.stage = stage
        self.provider = provider
        self.details = details or {}

    def __repr__(self) -> str:
        return (
            f"RegistrationError(provider={self.provider!r}, stage={self.stage.value!r}, "
            f"category={self.category.value!r}, message={self.message!r})"
        )


@dataclass
class RegistrationSession:
    """注册会话上下文与断点快照。"""
    provider: str
    session_id: str = field(default_factory=lambda: f"reg_{int(time.time()*1000)}")
    stage: RegistrationStage = RegistrationStage.INIT
    email: str = ""
    email_source: str = ""
    email_state: dict[str, Any] = field(default_factory=dict)
    proxy_used: str = ""
    captcha_token: str = ""
    verification_token: str = ""
    verification_code: str = ""
    verify_link: str = ""
    session_cookie: str = ""
    password: str = ""
    credits: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_error: str | None = None
    error_category: RegistrationErrorCategory | None = None

    def advance_to(self, stage: RegistrationStage, **kwargs: Any) -> None:
        """推进阶段并更新字段。"""
        self.stage = stage
        self.updated_at = time.time()
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        log.debug("注册会话 [%s][%s] 阶段推进 -> %s", self.provider, self.session_id, stage.value)

    def mark_failed(self, error: str, category: RegistrationErrorCategory) -> None:
        """标记当前会话失败并记录分类。"""
        self.stage = RegistrationStage.FAILED
        self.last_error = error
        self.error_category = category
        self.updated_at = time.time()

    def snapshot(self) -> dict[str, Any]:
        """输出不可变快照供观测与审计。"""
        return {
            "session_id": self.session_id,
            "provider": self.provider,
            "stage": self.stage.value,
            "email": self.email,
            "email_source": self.email_source,
            "has_captcha": bool(self.captcha_token),
            "has_verify_token": bool(self.verification_token),
            "has_code_or_link": bool(self.verification_code or self.verify_link),
            "credits": self.credits,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_error": self.last_error,
            "error_category": self.error_category.value if self.error_category else None,
        }


class AdaptiveRegistrationBackoff:
    """自适应分类退避管理器 (Adaptive Error Backoff)。"""

    def __init__(
        self,
        cf_backoff: float | None = None,
        email_backoff: float | None = None,
        ip_backoff: float | None = None,
        transient_base: float | None = None,
        transient_max: float | None = None,
    ) -> None:
        self.cf_backoff = cf_backoff or getattr(config, "REG_BACKOFF_CF", 30.0)
        self.email_backoff = email_backoff or getattr(config, "REG_BACKOFF_EMAIL", 60.0)
        self.ip_backoff = ip_backoff or getattr(config, "REG_BACKOFF_IP", 120.0)
        self.transient_base = transient_base or getattr(config, "REG_BACKOFF_TRANSIENT_BASE", 2.0)
        self.transient_max = transient_max or getattr(config, "REG_BACKOFF_TRANSIENT_MAX", 30.0)

        self._consecutive_errors: dict[str, int] = {}
        self._last_backoff: dict[str, float] = {}
        self._last_category: dict[str, RegistrationErrorCategory] = {}
        self._stats: dict[str, dict[str, int]] = {}

    def compute_backoff(self, provider: str, category: RegistrationErrorCategory) -> float:
        """根据故障类别与连续失败次数计算退避秒数。"""
        prov_stats = self._stats.setdefault(provider, {
            "cf_blocked": 0, "email_rate_limited": 0, "ip_blocked": 0, "transient": 0, "total": 0
        })
        prov_stats[category.value] = prov_stats.get(category.value, 0) + 1
        prov_stats["total"] = prov_stats.get("total", 0) + 1

        consecutive = self._consecutive_errors.get(provider, 0) + 1
        self._consecutive_errors[provider] = consecutive
        self._last_category[provider] = category

        if category == RegistrationErrorCategory.CF_BLOCKED:
            backoff = self.cf_backoff
        elif category == RegistrationErrorCategory.EMAIL_RATE_LIMITED:
            backoff = self.email_backoff
        elif category == RegistrationErrorCategory.IP_BLOCKED:
            backoff = self.ip_backoff
        else:
            # TRANSIENT: 2s, 4s, 8s, 16s, ... 最大 30s
            backoff = min(self.transient_base * (2 ** (consecutive - 1)), self.transient_max)

        self._last_backoff[provider] = backoff
        return backoff

    def record_success(self, provider: str) -> None:
        """成功时重置连续失败计数。"""
        self._consecutive_errors[provider] = 0

    def snapshot(self) -> dict[str, Any]:
        """返回退避管理器全局快照。"""
        return {
            "consecutive_errors": dict(self._consecutive_errors),
            "last_backoff": dict(self._last_backoff),
            "last_category": {k: v.value for k, v in self._last_category.items()},
            "stats": dict(self._stats),
        }


# 全局自适应退避单例
adaptive_backoff = AdaptiveRegistrationBackoff()


def _browser_headers(origin: str, referer: str | None = None) -> dict[str, str]:
    return {
        "User-Agent": config.USER_AGENT,
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": origin,
        "Referer": referer or (origin + "/"),
    }


async def _th(fn, *a, **k):
    """将同步 httpx.Client 调用丢入线程池，避免阻塞事件循环。"""
    return await asyncio.to_thread(fn, *a, **k)


def _extract_code(mail: dict | None) -> str | None:
    """从验证码邮件提取 6 位数字（同步正则快路径，供测试与历史调用）。"""
    if not mail:
        return None
    blob = str(mail.get("bodyPreview") or "") + str(mail.get("bodyHtml") or "") + str(mail.get("subject") or "")
    m = re.search(r"\b(\d{6})\b", blob)
    return m.group(1) if m else None


def _extract_verify_link(mail: dict | None) -> str | None:
    """从验证邮件提取 verify-email 链接（同步正则快路径，供测试与历史调用）。"""
    if not mail:
        return None
    blob = str(mail.get("bodyHtml") or "") + str(mail.get("bodyPreview") or "")
    m = re.search(r'https://[^\s"\'<>]+/api/auth/verify-email\?token=[^&\s"\'<>]+', blob)
    return m.group(0).replace("&amp;", "&") if m else None


def _proxy_host(proxy: str | None) -> str:
    """从代理字符串中提取主机/IP（形如 http://user:pass@host:port 或 socks5://host:port）。"""
    if not proxy:
        return ""
    s = proxy.split("://", 1)[-1]
    if "@" in s:
        s = s.split("@", 1)[-1]
    host = s.split(":", 1)[0]
    return host


def _ip_to_proxy(ip_or_proxy: str) -> str | None:
    """把 register_ip（可能是裸 IP 或完整代理串）还原成签到可用出口。

    优先从代理池里找一个 host 与 register_ip 匹配的条目（地址复用，token 绑定同 IP）；
    匹配不到时返回 register_ip 本身（若是完整代理则原样，若是裸 IP 则直连 = None）。
    """
    ip_or_proxy = (ip_or_proxy or "").strip()
    if not ip_or_proxy:
        return None
    # 已是完整代理（含 :// 或 host:port）
    if "://" in ip_or_proxy or ":" in ip_or_proxy.replace("://", ""):
        return ip_or_proxy
    # 裸 IP：在池里找 host 相同者（若存在），否则直连
    try:
        from .proxy_pool import proxy_pool
        host_target = ip_or_proxy
        for entry in proxy_pool.entries:
            if _proxy_host(entry.url) == host_target:
                return entry.url
    except Exception:
        pass
    return None


def _mail_ai_extract_enabled() -> bool:
    """AI 兜底邮件提取总开关：IF_MAIL_AI_EXTRACT=1 且能拿到配置。"""
    try:
        from .mail_extract import _ai_enabled
        return _ai_enabled()
    except Exception:
        return False


def _gen_password() -> str:
    """生成高强度随机密码，避免同秒注册使用相同密码被风控判定。

    由 secrets 生成 16 字符，保证大小写字母、数字、特殊符号混合。
    """
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(16))
        if (
            any(c.islower() for c in pw)
            and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in "!@#$%^&*" for c in pw)
        ):
            return pw


def _session_data_from_cookies(cookies: httpx.Cookies) -> str:
    """从登录响应 cookies 提取 better-auth session_data（用于后续鉴权续期）。"""
    for name in ("__Secure-better-auth.session_data", "better-auth.session_data"):
        if name in cookies:
            return cookies[name]
    return ""


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

    def _ensure_client(self, email: str = "", force_rotate: bool = False) -> None:
        if force_rotate:
            want = config.PROXY
        else:
            want = self.proxy or config.PROXY

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

        if MOCK_REGISTER:
            import random
            email = f"mocknb{int(time.time())}{random.randint(0, 999)}@mock.com"
            session.advance_to(RegistrationStage.COMPLETED, email=email, credits=4)
            adaptive_backoff.record_success(self.provider)
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
                src_name = (src or {}).get("source", "unknown") if isinstance(src, dict) else getattr(src, "name", "unknown")
                session.advance_to(
                    RegistrationStage.EMAIL_ALLOCATED,
                    email=email,
                    email_source=src_name,
                    email_state=src if isinstance(src, dict) else {},
                )
            except Exception as e:
                err_str = str(e)
                cat = RegistrationErrorCategory.EMAIL_RATE_LIMITED if "429" in err_str or "限流" in err_str else RegistrationErrorCategory.TRANSIENT
                raise RegistrationError(f"邮箱池分配失败: {e}", category=cat, stage=RegistrationStage.INIT, provider=self.provider)

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
                raise RegistrationError(f"Turnstile 求解失败: {e}", category=RegistrationErrorCategory.CF_BLOCKED, stage=RegistrationStage.EMAIL_ALLOCATED, provider=self.provider)

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
                raise RegistrationError(f"注册请求异常: {e}", category=RegistrationErrorCategory.TRANSIENT, stage=RegistrationStage.CAPTCHA_SOLVED, provider=self.provider)

            if r.status_code == 403:
                self._ensure_client(email, force_rotate=True)
                raise RegistrationError(f"sign-up 触发 403 风控", category=RegistrationErrorCategory.IP_BLOCKED, stage=RegistrationStage.CAPTCHA_SOLVED, provider=self.provider)
            if r.status_code == 429:
                raise RegistrationError(f"sign-up 触发 429 限流", category=RegistrationErrorCategory.EMAIL_RATE_LIMITED, stage=RegistrationStage.CAPTCHA_SOLVED, provider=self.provider)
            if r.status_code != 200:
                email_pool.record(email, self.provider, "error", "signup_fail")
                resp_text = str(r.text)[:150]
                # INVALID_EMAIL → 域名已被上游拉黑，记入 domain_risk，下次分配跳过该域名
                if "invalid_email" in resp_text.lower() or "invalid email" in resp_text.lower():
                    cat = RegistrationErrorCategory.EMAIL_RATE_LIMITED
                elif "turnstile" in resp_text.lower() or "captcha" in resp_text.lower():
                    cat = RegistrationErrorCategory.CF_BLOCKED
                else:
                    cat = RegistrationErrorCategory.IP_BLOCKED if r.status_code in (401, 403) else RegistrationErrorCategory.TRANSIENT
                raise RegistrationError(f"sign-up 失败 HTTP {r.status_code}: {resp_text}", category=cat, stage=RegistrationStage.CAPTCHA_SOLVED, provider=self.provider)

            session.advance_to(RegistrationStage.VERIFICATION_SENT)

            # 阶段 4: 收取验证链接（如超时仍允许尝试直接登录）
            mail = await email_pool.wait_for_mail(email, session.email_state, 90.0, "Verify")
            link = _extract_verify_link(mail)
            if not link and _mail_ai_extract_enabled():
                # AI 兜底：正则未命中时尝试 LLM 提取（默认关闭，失败返回 None 不阻塞）
                from .mail_extract import extract_verify_link as _ai_extract_link
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
                raise RegistrationError(f"sign-in 请求网络异常: {e}", category=RegistrationErrorCategory.TRANSIENT, stage=RegistrationStage.CODE_OR_LINK_RECEIVED, provider=self.provider)

            # 从 client jar 提取累积的全部 cookies（含重定向/其它响应累积的 __Secure-better-auth.session_data 等），
            # 而非仅 login 响应 cookies。
            cookie = "; ".join(f"{k}={v}" for k, v in self.client.cookies.items())
            if login.status_code == 400 or "__Secure-better-auth.session_token" not in self.client.cookies:
                email_pool.record(email, self.provider, "error", "login_fail")
                if login.status_code == 403:
                    self._ensure_client(email, force_rotate=True)
                    cat = RegistrationErrorCategory.IP_BLOCKED
                elif login.status_code == 429:
                    cat = RegistrationErrorCategory.EMAIL_RATE_LIMITED
                else:
                    cat = RegistrationErrorCategory.TRANSIENT
                raise RegistrationError(f"登录失败 HTTP {login.status_code}: {str(login.text)[:120]}", category=cat, stage=RegistrationStage.CODE_OR_LINK_RECEIVED, provider=self.provider)

            session.advance_to(RegistrationStage.LOGGED_IN, session_cookie=cookie, credits=4)
            session_data = _session_data_from_cookies(self.client.cookies)
            email_pool.record(email, self.provider, "ok", note="no_verify" if not link else "verified")
            adaptive_backoff.record_success(self.provider)
            session.advance_to(RegistrationStage.COMPLETED)
            log.info("nanobanana 注册成功 %s credits=4 (session: %s, has_session_data=%s)", email, session.session_id, bool(session_data))

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
            return None
        except Exception as err:
            session.mark_failed(str(err), RegistrationErrorCategory.TRANSIENT)
            backoff_sec = adaptive_backoff.compute_backoff(self.provider, RegistrationErrorCategory.TRANSIENT)
            log.warning("nanobanana 发生未捕获异常退避 %.1fs: %s", backoff_sec, err)
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
        if MOCK_REGISTER:
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
                bal = await _th(
                    self.client.get,
                    f"{self.base}/api/credits/balance",
                    headers={"Cookie": cookie, "User-Agent": config.USER_AGENT},
                )
                return int((bal.json() or {}).get("credits", 0))

            # 步骤 2：Server Action 领取（需要 captcha 则同一出口解）
            body = [{"captchaToken": ""}]
            if data.get("requiresCaptcha"):
                try:
                    captcha, _ = await turnstile_client.solve_turnstile(
                        config.CF_SOLVER_URL,
                        self.turnstile_page,
                        self.SITEKEY,
                        config.TURNSTILE_TIMEOUT,
                        proxy=config.PROXY,   # 同一出口，与登录一致
                    )
                    body = [{"captchaToken": captcha}]
                except Exception:
                    return None

            payload = json.dumps(body).replace("$", "$$") if "$" in json.dumps(body) else json.dumps(body)
            r = await _th(
                self.client.post,
                f"{self.base}/zh",
                headers={
                    "Cookie": cookie,
                    "User-Agent": config.USER_AGENT,
                    "Next-Action": ACTION_CLAIM_DAILY_CHECKIN,
                    "Accept": "text/x-component",
                    "Content-Type": "text/plain;charset=UTF-8",
                },
                content=payload,
            )

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

            bal = await _th(
                self.client.get,
                f"{self.base}/api/credits/balance",
                headers={"Cookie": cookie, "User-Agent": config.USER_AGENT},
            )
            return int((bal.json() or {}).get("credits", 0))
        except Exception as e:
            log.warning("nanobanana 签到失败 %s: %s", acc.get("email", "?"), e)
        return None

    async def re_login(self, email: str, password: str) -> dict | None:
        """cookie 失效后重新登录（Turnstile 求解 + sign-in 端点），返回新会话 cookie。

        复用 register_one 的登录流程：代理修复 + Turnstile 求解 + POST /api/auth/sign-in/email，
        从 client cookie jar 汇总 __Secure-better-auth 会话 cookie，并顺带取 session_data。
        """
        if MOCK_REGISTER:
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
            if login.status_code == 400 or "__Secure-better-auth.session_token" not in self.client.cookies or not cookie:
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
