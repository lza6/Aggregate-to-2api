"""tests/test_skills_loader.py — P1-A1 skills 四件套加载器测试。

验收：
- AGENT_SKILLS_ENABLED=1 默认开
- skill_index 扫描 api/skills/<scene>/SKILL.md 建 frontmatter 索引
- get_skills_for(names) 命中已注册 skill → 聚合描述段
- get_skills_for([]) 回退占位串（零回归）
- get_skills_for(["不存在的"]) 记 warn 返回"无可用 skill"
- IF_AGENT_SKILLS_ENABLED=0 关闭 → 全部回退占位串
"""

from __future__ import annotations

import os

# 触发 IF_AGENT_SKILLS_ENABLED 默认开启（conftest autouse 复位 settings 后仍读 env）
os.environ.setdefault("IF_AGENT_SKILLS_ENABLED", "1")


def test_agent_skills_enabled_default():
    """P1-A1 开关默认开启。"""
    from api.skills import AGENT_SKILLS_ENABLED

    assert AGENT_SKILLS_ENABLED is True


def test_skill_index_scans_built_in_skills():
    """skill_index 扫描建索引，image_quality/prompt_refine/critic 三 skill 命中。"""
    from api.skills import clear_cache, skill_index

    clear_cache()
    names = skill_index.names()
    assert "image-quality-check" in names, f"image-quality-check 未命中: {names}"
    assert "prompt-refine" in names, f"prompt-refine 未命中: {names}"
    assert "critic-review" in names, f"critic-review 未命中: {names}"


def test_load_skill_returns_record():
    """load_skill(name) 返回 SkillRecord（含 description + body）。"""
    from api.skills import clear_cache, load_skill

    clear_cache()
    rec = load_skill("critic-review")
    assert rec is not None
    assert "终检" in rec.description or "critic" in rec.description.lower()
    assert "## 触发条件" in rec.body


def test_get_skills_for_hits_returns_description_list():
    """get_skills_for 命中 skill → 聚合 ``- name: description`` 列表。"""
    from api.skills import clear_cache, get_skills_for

    clear_cache()
    text = get_skills_for(["critic-review", "image-quality-check"])
    assert "- critic-review:" in text
    assert "- image-quality-check:" in text


def test_get_skills_for_empty_returns_placeholder():
    """get_skills_for([]) 回退占位串（向后兼容）。"""
    from api.skills import clear_cache, get_skills_for

    clear_cache()
    text = get_skills_for([])
    assert "P1-A1" in text or "启用后填充" in text


def test_get_skills_for_missing_skill_warns(monkeypatch, caplog):
    """get_skills_for 引用不存在的 skill → 记 warn，返回"无可用 skill"。"""
    import logging

    from api.skills import clear_cache, get_skills_for

    clear_cache()
    with caplog.at_level(logging.WARNING, logger="skills.loader"):
        text = get_skills_for(["totally-nonexistent-skill"])
    assert "无可用 skill" in text or "P1-A1" in text
    assert "totally-nonexistent-skill" in caplog.text


def test_get_skills_for_disabled_returns_placeholder(monkeypatch):
    """IF_AGENT_SKILLS_ENABLED=0 → 全部回退占位串（零回归）。"""
    from api.skills import clear_cache, get_skills_for

    clear_cache()
    # 临时关闭开关
    import api.skills as skills_pkg

    monkeypatch.setattr(skills_pkg, "AGENT_SKILLS_ENABLED", False)
    text = get_skills_for(["critic-review"])
    assert "P1-A1" in text or "启用后填充" in text


def test_compose_system_text_injects_skills_into_template():
    """compose_system_text 把 skills 描述段注入 {skills} 变量。"""
    from api.prompts import compose_system_text
    from api.skills import clear_cache

    clear_cache()
    # meta 含 system_prompt_template + skills，验证 skills 变量被填充
    composed = compose_system_text(
        "user-system",
        {
            "system_prompt_template": "anthropic_v5_chat",
            "skills": ["critic-review"],
        },
    )
    # skills 变量应被替换为描述段，不再是裸占位符 {skills}
    assert "{skills}" not in composed
    assert "critic-review" in composed or "P1-A1" in composed


def test_compose_system_text_no_skills_key_returns_user_system():
    """无 system_prompt_template 键 → compose_system_text 原样返回 user_system（零回归）。"""
    from api.prompts import compose_system_text

    composed = compose_system_text("just-user", None)
    assert composed == "just-user"
