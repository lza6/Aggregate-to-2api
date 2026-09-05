"""注册器辅助工具：HTTP headers / 邮件提取 / 代理解析 / 密码生成（P0-5 从 registerer.py 拆出）。

向后兼容：`api.registerer` 旧路径仍 re-export 全部符号。
"""

from __future__ import annotations

import asyncio
import re
import secrets
from typing import Any

import httpx

from .. import config


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
        from ..proxy_pool import proxy_pool

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
        from ..mail_extract import _ai_enabled

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


__all__ = [
    "_browser_headers",
    "_extract_code",
    "_extract_verify_link",
    "_gen_password",
    "_ip_to_proxy",
    "_mail_ai_extract_enabled",
    "_parse_iso_ts",
    "_proxy_host",
    "_session_data_from_cookies",
    "_th",
]


def _re_export_parse_iso() -> Any:
    """避免循环：_parse_iso_ts 实际定义在 types.py，这里 re-export。"""
    from .types import _parse_iso_ts as _p

    return _p


# re-export _parse_iso_ts（实际定义在 types.py，保持旧 import 路径可用）
from .types import _parse_iso_ts  # noqa: E402,F401
