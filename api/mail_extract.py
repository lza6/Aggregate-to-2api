"""邮件验证码 / 验证链接提取：正则快路径 + 可选 LLM 兜底。

设计（借鉴 cloudflare_temp_email 的 AI 邮件识别思路，但严格适配主项目约束）：
- **默认仅用正则快路径**，行为与历史完全一致、零回归风险。
- 仅当启用 ``IF_MAIL_AI_EXTRACT=1`` 且正则未命中时，才降级调用 LLM 兜底，
  用于从难以用正则覆盖的邮件中提取验证码 / 验证链接。
- LLM 通道复用 TryingOpen 聊天提供商（``chat_collect``），不新增第三方依赖。
- LLM 调用失败或返回非法结构时**严格返回 None**，绝不阻塞注册主流程。

调用方：``api/registerer.py`` 的 ``_extract_code`` / ``_extract_verify_link``
（两者委托到本模块，保持函数签名与历史行为兼容）。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from . import config

log = logging.getLogger("mail_extract")

# 正则快路径（与 registerer 历史逻辑一致）
_CODE_RE = re.compile(r"\b(\d{6})\b")
_VERIFY_LINK_RE = re.compile(r'https://[^\s"\'<>]+/api/auth/verify-email\?token=[^&\s"\'<>]+')

# 从历史邮件文本中兜底抓任意 https 验证链接（含非 /api/auth/verify-email 路径）
_ANY_LINK_RE = re.compile(r"https?://[^\s\"'<>]+")


def _mail_blob(mail: dict | None, prefer_html: bool = False) -> str:
    """拼接邮件可读文本。"""
    if not mail:
        return ""
    if prefer_html:
        return (
            str(mail.get("bodyHtml") or "")
            + str(mail.get("bodyPreview") or "")
            + str(mail.get("subject") or "")
        )
    return (
        str(mail.get("bodyPreview") or "")
        + str(mail.get("bodyHtml") or "")
        + str(mail.get("subject") or "")
    )


def _regex_code(mail: dict | None) -> str | None:
    m = _CODE_RE.search(_mail_blob(mail))
    return m.group(1) if m else None


def _regex_verify_link(mail: dict | None) -> str | None:
    m = _VERIFY_LINK_RE.search(_mail_blob(mail, prefer_html=True))
    return m.group(0).replace("&amp;", "&") if m else None


# ── LLM 兜底（默认关闭）─────────────────────────────

# 允许注入的聊天调用函数签名：(model, messages) -> dict（含 text / reasoning）
_ChatFn = Callable[..., Any]


async def _ai_extract_kind(
    mail: dict | None,
    kind: str,
    chat_fn: _ChatFn,
    model: str,
    timeout: float = 30.0,
) -> str | None:
    """调用 LLM 从邮件中提取验证码 / 验证链接。kind ∈ {"code", "link"}。"""
    if not mail:
        return None
    blob = json.dumps(mail, ensure_ascii=False, default=str)[:3000]
    if kind == "code":
        instruction = (
            "请从以下临时邮箱收到的验证码邮件中提取 6 位数字验证码。"
            "只输出 JSON：{\"code\":\"123456\"}；找不到则 {\"code\":null}。"
        )
    else:
        instruction = (
            "请从以下临时邮箱收到的验证邮件中提取用于邮箱验证的 https 链接。"
            "只输出 JSON：{\"link\":\"https://...\"}；找不到则 {\"link\":null}。"
        )
    system = "你是邮件验证码提取助手。只输出合法 JSON，不要解释。"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"{instruction}\n\n邮件内容：\n{blob}"},
    ]
    try:
        result = await chat_fn(model, messages)
    except Exception as exc:  # 网络/超时/上游错误 → 兜底失败，返回 None
        log.warning("邮件 %s AI 提取失败: %s", kind, exc)
        return None
    text = str(result.get("text") or "") if isinstance(result, dict) else str(result)
    parsed = _parse_ai_json(text)
    if kind == "code":
        value = parsed.get("code") if isinstance(parsed, dict) else None
        return str(value).strip() if isinstance(value, str) and value.strip() else None
    value = parsed.get("link") if isinstance(parsed, dict) else None
    if isinstance(value, str):
        m = _ANY_LINK_RE.search(value)
        if m:
            return m.group(0).replace("&amp;", "&")
    # 无 JSON 但文本中有链接 → 直接提取
    m = _ANY_LINK_RE.search(text)
    if m:
        return m.group(0).replace("&amp;", "&")
    return None


def _parse_ai_json(text: str) -> dict[str, Any] | None:
    """从 LLM 输出中解析 JSON，容忍前后缀与 markdown 代码块。"""
    if not text:
        return None
    candidates = [text]
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
    if m:
        candidates.insert(0, m.group(1))
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    # 最后尝试抓取最外层 {...}
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return None


def _ai_enabled() -> bool:
    try:
        return bool(config.IF_MAIL_AI_EXTRACT)
    except Exception:
        return False


def _default_chat_fn() -> tuple[_ChatFn, str] | None:
    """构造默认 LLM 通道：TryingOpen 聊天提供商 + 一个可用模型。

    返回 (chat_collect, model_id)；任一不可用返回 None（降级为纯正则）。
    """
    try:
        from .providers.registry import bootstrap, registry
        bootstrap()
        prefix = "tryingopen"
        provider = registry.chat_providers.get(prefix)
        if provider is None or not provider.all_models():
            return None
        model_id = sorted(provider.all_models())[0].id
        return provider.chat_collect, model_id
    except Exception:
        log.debug("构造默认 LLM 邮件提取通道失败，回退纯正则")
        return None


async def extract_code(
    mail: dict | None,
    ai: bool | None = None,
    chat_fn: _ChatFn | None = None,
    model: str | None = None,
) -> str | None:
    """提取 6 位验证码。ai 默认取配置 IF_MAIL_AI_EXTRACT；可显式覆盖以便测试。"""
    code = _regex_code(mail)
    if code is not None:
        return code
    use_ai = _ai_enabled() if ai is None else ai
    if not use_ai:
        return None
    if chat_fn is None:
        default = _default_chat_fn()
        if default is None:
            return None
        chat_fn, model = default
    return await _ai_extract_kind(mail, "code", chat_fn, model or "")


async def extract_verify_link(
    mail: dict | None,
    ai: bool | None = None,
    chat_fn: _ChatFn | None = None,
    model: str | None = None,
) -> str | None:
    """提取验证链接。ai 默认取配置 IF_MAIL_AI_EXTRACT；可显式覆盖以便测试。"""
    link = _regex_verify_link(mail)
    if link is not None:
        return link
    use_ai = _ai_enabled() if ai is None else ai
    if not use_ai:
        return None
    if chat_fn is None:
        default = _default_chat_fn()
        if default is None:
            return None
        chat_fn, model = default
    return await _ai_extract_kind(mail, "link", chat_fn, model or "")
