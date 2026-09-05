"""Skills 加载器：扫描 ``api/skills/<scene>/SKILL.md`` frontmatter 索引 + 缓存。

设计（参考 claude-skills-main SKILL-AUTHORING-STANDARD）：
- 每个 skill 一个目录 ``api/skills/<name>/``，含 ``SKILL.md``（frontmatter + 正文）
- frontmatter ``name`` + ``description`` 是唯一可发现性入口
- 加载器启动时扫一遍建索引（name → {description, dir, body}），缓存正文
- ``get_skills_for(names)`` 按 meta.skills 列出的 name 聚合描述段
- 文件变更触发索引重建（基于 mtime 失效，避免每次 chat 全量扫描）

不照抄 claude-skills 全文（版权风险），只自写骨架 + frontmatter 解析。
加载失败记 warn 返回空串，不崩主链路（向后兼容：无 skill 走原占位串）。
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("skills.loader")

_SKILLS_ROOT = Path(__file__).resolve().parent
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_CACHE_TTL_SECONDS = 60.0  # 索引缓存 60s（文件 watcher + mtime 双重失效）


@dataclass(frozen=True)
class SkillRecord:
    """单个 skill 的索引记录。"""

    name: str
    description: str
    scene: str  # 所属场景目录名
    body: str  # SKILL.md 正文（剥离 frontmatter 后）
    path: str  # SKILL.md 绝对路径


@dataclass
class SkillIndex:
    """skills 索引：name → SkillRecord。带 mtime 缓存失效。"""

    root: Path = field(default_factory=lambda: _SKILLS_ROOT)
    _records: dict[str, SkillRecord] = field(default_factory=dict)
    _loaded_at: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _scan_dir(self) -> dict[str, SkillRecord]:
        """扫描 root 下所有 ``<scene>/SKILL.md``，解析 frontmatter 建索引。"""
        records: dict[str, SkillRecord] = {}
        if not self.root.exists():
            return records
        for skill_md in self.root.rglob("SKILL.md"):
            try:
                text = skill_md.read_text(encoding="utf-8")
            except OSError as exc:
                log.warning("skill 读取失败 %s: %s", skill_md, exc)
                continue
            name, description, body = self._parse_frontmatter(text, skill_md)
            if not name:
                continue
            scene = skill_md.parent.name
            records[name] = SkillRecord(
                name=name,
                description=description,
                scene=scene,
                body=body,
                path=str(skill_md),
            )
        return records

    @staticmethod
    def _parse_frontmatter(text: str, path: Path) -> tuple[str, str, str]:
        """解析 ``---\\nname: ...\\ndescription: ...\\n---\\n<body>`` frontmatter。

        宽容解析：无 frontmatter 时把文件名当 name，首段当 description。
        """
        match = _FRONTMATTER_RE.match(text)
        if match:
            header = match.group(1)
            body = match.group(2).strip()
            name = ""
            description = ""
            for line in header.splitlines():
                if ":" not in line:
                    continue
                key, _, value = line.partition(":")
                key = key.strip().lower()
                value = value.strip().strip('"').strip("'")
                if key == "name":
                    name = value
                elif key == "description":
                    description = value
            if not name:
                name = path.parent.name
            return name, description, body
        # 无 frontmatter：文件名当 name，首行当 description
        name = path.parent.name
        first_line = text.strip().split("\n", 1)[0].strip("# ").strip()
        return name, first_line, text.strip()

    def _is_stale(self) -> bool:
        """缓存是否过期（TTL 或 root mtime 变化）。"""
        if not self._records:
            return True
        if time.time() - self._loaded_at > _CACHE_TTL_SECONDS:
            return True
        try:
            root_mtime = self.root.stat().st_mtime_ns
            for rec in self._records.values():
                p = Path(rec.path)
                if not p.exists():
                    return True
                if p.stat().st_mtime_ns > root_mtime:
                    return True
        except OSError:
            return True
        return False

    def refresh(self) -> int:
        """重建索引。返回 skill 数。"""
        with self._lock:
            self._records = self._scan_dir()
            self._loaded_at = time.time()
            return len(self._records)

    def get(self, name: str) -> SkillRecord | None:
        """按 name 取 skill 记录（必要时先 refresh）。"""
        if self._is_stale():
            self.refresh()
        return self._records.get(name)

    def all(self) -> list[SkillRecord]:
        """全部 skill 记录（必要时先 refresh）。"""
        if self._is_stale():
            self.refresh()
        return list(self._records.values())

    def names(self) -> list[str]:
        """全部 skill name（供 /v1/agent/skills 端点）。"""
        if self._is_stale():
            self.refresh()
        return sorted(self._records.keys())


# 模块级单例（全服务共享；测试可用 clear_cache 重置）
skill_index = SkillIndex()


def load_skill(name: str) -> SkillRecord | None:
    """加载单个 skill 记录。不存在返回 None（不崩）。"""
    return skill_index.get(name)


def get_skills_for(names: list[str] | None) -> str:
    """按 meta.skills 列出的 name 聚合描述段，注入模板 ``{skills}`` 变量。

    - names 为空或 None → 返回占位串"（P1-A1 启用后填充）"（向后兼容）
    - 命中的 skill → 聚合 ``- <name>: <description>`` 列表
    - 未命中的 name → 记 warn 但不崩（降级为空）
    """
    from . import AGENT_SKILLS_ENABLED

    if not AGENT_SKILLS_ENABLED or not names:
        return "（P1-A1 启用后填充）"
    lines: list[str] = []
    for name in names:
        rec = skill_index.get(name)
        if rec is None:
            log.warning("skill 未找到：%s（meta.skills 引用了不存在的 skill）", name)
            continue
        lines.append(f"- {rec.name}: {rec.description}")
    if not lines:
        return "（无可用 skill）"
    return "\n".join(lines)


def clear_cache() -> None:
    """测试钩子：清缓存。"""
    with skill_index._lock:
        skill_index._records = {}
        skill_index._loaded_at = 0.0


__all__ = [
    "SkillIndex",
    "SkillRecord",
    "clear_cache",
    "get_skills_for",
    "load_skill",
    "skill_index",
]
