"""模板加载器：从 api/prompts/templates/*.md 加载，缓存渲染结果。

不照抄 CL4R1T4S 全文（版权风险），只自写骨架模板 + 变量插值。
加载失败记 warn 返回空串，不崩主链路（向后兼容：无模板走原 [SYSTEM INSTRUCTIONS]）。
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("prompts.loader")

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_CACHE: dict[str, str] = {}
_LOCK = threading.Lock()


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("提示词模板读取失败 %s: %s", path, exc)
        return ""


def load_template(name: str) -> str:
    """按名加载模板正文（不含变量插值）。不存在记 warn 返回空串。"""
    if not name:
        return ""
    with _LOCK:
        cached = _CACHE.get(name)
        if cached is not None:
            return cached
        path = _TEMPLATES_DIR / f"{name}.md"
        text = _read_file(path) if path.exists() else ""
        if not text:
            log.warning("提示词模板未找到或为空：%s（走原 [SYSTEM INSTRUCTIONS] 路径）", name)
        _CACHE[name] = text
        return text


def render_template(template_body: str, variables: dict[str, Any]) -> str:
    """变量插值：{var} → str(var)。未在 variables 的占位符原样保留（不崩）。"""
    if not template_body:
        return ""
    rendered = template_body
    for key, value in variables.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def strip_header_comment(template_body: str) -> str:
    """剥离模板头部注释行（# 开头标题行与 > 引用说明行，至第一个空行结束的说明块）。

    模板文件头部的 `> 变量：{...}` 说明行含未插值占位符示例，会原样进入最终 system
    造成困惑，故在渲染前剥离（保留正文小节标题 `## `）。
    """
    if not template_body:
        return ""
    lines = template_body.split("\n")
    out: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if not skipping:
            if stripped.startswith(">") or (stripped.startswith("# ") and out == []):
                skipping = True
                continue
            out.append(line)
        else:
            # 说明块进行中：空行结束说明块，或仍是 > / 注释行继续跳过
            if stripped == "":
                skipping = False
                continue
            if stripped.startswith(">"):
                continue
            skipping = False
            out.append(line)
    return "\n".join(out).strip()


def build_system_prompt(
    user_system: str,
    template_name: str | None,
    variables: dict[str, Any],
) -> str:
    """完整组合：base 宪法 + 渲染后模板 + 用户 system。template_name 为 None 走原路径。"""
    if not template_name:
        return user_system
    base = load_template("base")
    body = render_template(strip_header_comment(load_template(template_name)), variables)
    parts = [p for p in (base, body, user_system) if p and p.strip()]
    return "\n\n---\n\n".join(parts) if parts else (user_system or "")


def clear_cache() -> None:
    """测试钩子：清缓存。"""
    with _LOCK:
        _CACHE.clear()


__all__ = ["build_system_prompt", "clear_cache", "load_template", "render_template"]
