"""kookeey 住宅代理接入：与 chatgpt2api 同款格式，每注册邮箱一个粘性 IP。

用途：
- 号池自动注册/批量注册的出口代理（每号独立住宅 IP，防批量注册同 IP 风控）
- aifreeforever 每 IP 每日限额场景的付费高质量轮换

kookeey 动态代理格式（官方教程）：
  ``UserID-SecurityUser:SecurityPass-CountryISO-RandomSession@gate:port``
  带 RandomSession = 粘性会话（同 session 固定 IP）；不带则每次请求换 IP。
  这里用 email 派生 session（md5[:8]）→ 同一账号稳定同一 IP，不同账号不同 IP。

安全：凭据不硬编码进源码。通过环境变量注入（与 chatgpt2api 同款 kookeey 账户）：
  IF_KOOKEEY_ENABLED / IF_KOOKEEY_USER_ID / IF_KOOKEEY_SEC_USER / IF_KOOKEEY_SEC_PASS /
  IF_KOOKEEY_GATE / IF_KOOKEEY_COUNTRY
未配置凭据时 disabled（kookeey_proxy_for 返回空串，注册走 proxy_pool 或直连）。
"""
from __future__ import annotations

import hashlib
import logging
import os
from urllib.parse import quote

from . import config

log = logging.getLogger("kookeey")


def _settings() -> dict:
    s = {
        "enabled": os.getenv("IF_KOOKEEY_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"},
        "scheme": os.getenv("IF_KOOKEEY_SCHEME", "http"),
        "gate_host": os.getenv("IF_KOOKEEY_GATE", "gate.kookeey.info"),
        "gate_port": int(os.getenv("IF_KOOKEEY_GATE_PORT", "1000")),
        "user_id": os.getenv("IF_KOOKEEY_USER_ID", "").strip(),
        "security_username": os.getenv("IF_KOOKEEY_SEC_USER", "").strip(),
        "security_password": os.getenv("IF_KOOKEEY_SEC_PASS", "").strip(),
        "country": os.getenv("IF_KOOKEEY_COUNTRY", "US").strip(),
        "proxy_enabled": os.getenv("IF_KOOKEEY_PROXY_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"},
    }
    return s


def kookeey_proxy_for(email: str = "") -> str:
    """为指定邮箱构造 kookeey 粘性住宅代理 URL。

    同一 email → 同一 session（md5 前 8 位）→ 同一住宅 IP（粘性会话）；
    不同 email → 不同 IP。未启用/配置不全 → 返回空串（调用方回退）。
    空 email → 不带 session（每次请求轮换 IP）。
    """
    s = _settings()
    if not (s["enabled"] and s["proxy_enabled"]):
        return ""
    user_id = str(s["user_id"]).strip()
    sec_user = str(s["security_username"]).strip()
    sec_pass = str(s["security_password"]).strip()
    gate_host = str(s["gate_host"]).strip()
    if not (user_id and sec_user and sec_pass and gate_host):
        return ""
    country = str(s["country"]).strip() or "US"
    session = hashlib.md5(str(email or "").strip().lower().encode("utf-8")).hexdigest()[:8]
    # 凭据可能含 @ : / 等 URL 保留字符，user/pass 分段 percent-encode
    auth = f"{user_id}-{quote(sec_user, safe='')}:{quote(sec_pass, safe='')}-{country}-{session}"
    return f"{s['scheme']}://{auth}@{gate_host}:{s['gate_port']}"


def kookeey_enabled() -> bool:
    s = _settings()
    return bool(s["enabled"] and s["proxy_enabled"] and s["user_id"] and s["gate_host"])
