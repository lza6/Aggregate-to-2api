"""Skills 体系（P1-A1，CL4R1T4S + claude-skills 提炼）。

agent 化第一步：激活 ``ModelSpec.meta.skills`` 占位。每个 skill = SKILL.md
(frontmatter) + scripts/ + references/ + assets/ 四件套，frontmatter
``name`` + ``description`` 是唯一可发现性入口。

挂载点：``api/prompts/__init__.py:compose_system_text`` 已把 ``meta.skills``
作为 ``{skills}`` 变量注入模板；本包提供加载器扫描 frontmatter 索引 +
缓存，按 ``meta.skills`` 列出的 skill 名聚合描述段注入模板。

开关：``IF_AGENT_SKILLS_ENABLED=0`` 关闭，回退原 ``meta.skills`` 占位串
"（P1-1 启用后填充）"，行为零回归（向后兼容）。

层次（参考 skills-best-practices 三层层级）：
- Planning skills：多步规划（如 critic 终检、decomposer 任务分解）
- Functional skills：单域能力（如图像生成参数建议、视频脚本结构）
- Atomic skills：原子动作（如尺寸校验、水印检测）
"""

from __future__ import annotations

import logging
import os

from .loader import SkillIndex, clear_cache, get_skills_for, load_skill, skill_index

log = logging.getLogger("skills")

# P1-A1 开关：默认开启，回滚置 0 即回退原 meta.skills 占位串
AGENT_SKILLS_ENABLED = os.getenv("IF_AGENT_SKILLS_ENABLED", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

__all__ = [
    "AGENT_SKILLS_ENABLED",
    "SkillIndex",
    "clear_cache",
    "get_skills_for",
    "load_skill",
    "skill_index",
]
