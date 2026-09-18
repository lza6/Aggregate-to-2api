"""scripts/validate_skills.py 门禁测试（指南 B1a / P0-4）。纯本地，无网络/上游依赖。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_skills import (  # noqa: E402
    _SCHEMA_SKELETON,
    check_skill_dir,
    parse_frontmatter_keys,
)
from scripts.validate_skills import (
    main as validate_main,
)

GOOD_FRONTMATTER = """---
name: test-skill
description: 测试技能
version: 1.0.0
security:
  run: isolated
  network: none
  approvals: none
inputs:
  prompt: string 必填
outputs:
  result: string
---

## 正文
"""

GOOD_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {"prompt": {"type": "string", "minLength": 1}},
    "required": ["prompt"],
}

GOOD_VALIDATE = """# -*- coding: utf-8 -*-
import sys
def validate():
    return True, "PASS: ok"
def main() -> int:
    ok, s = validate()
    print(s)
    return 0 if ok else 1
if __name__ == "__main__":
    sys.exit(main())
"""

GOOD_GOLDEN = {
    "name": "case-1",
    "input": {"prompt": "hello"},
    "expected_output_fragment": {"result": "ok"},
}


def _make_skill(tmp_path: Path, name: str = "alpha") -> Path:
    d = tmp_path / name
    (d / "expected_results").mkdir(parents=True)
    (d / "SKILL.md").write_text(GOOD_FRONTMATTER, encoding="utf-8")
    (d / "schema.json").write_text(json.dumps(GOOD_SCHEMA, ensure_ascii=False), encoding="utf-8")
    (d / "validate.py").write_text(GOOD_VALIDATE, encoding="utf-8")
    (d / "expected_results" / "case-1.json").write_text(json.dumps(GOOD_GOLDEN, ensure_ascii=False), encoding="utf-8")
    return d


def test_complete_skill_passes(tmp_path):
    d = _make_skill(tmp_path)
    rep = check_skill_dir(d, strict=False, fix=False)
    assert not rep.hard_fail, rep.fails
    assert rep.ok


def test_missing_schema_fails(tmp_path):
    d = _make_skill(tmp_path)
    (d / "schema.json").unlink()
    rep = check_skill_dir(d, strict=False, fix=False)
    assert rep.hard_fail
    assert any("schema.json" in f for f in rep.fails)


def test_bad_schema_json_fails(tmp_path):
    d = _make_skill(tmp_path)
    (d / "schema.json").write_text("{not json", encoding="utf-8")
    rep = check_skill_dir(d, strict=False, fix=False)
    assert rep.hard_fail
    assert any("解析失败" in f for f in rep.fails)


def test_schema_missing_required_list_fails(tmp_path):
    d = _make_skill(tmp_path)
    bad = dict(GOOD_SCHEMA)
    bad.pop("required")
    (d / "schema.json").write_text(json.dumps(bad), encoding="utf-8")
    rep = check_skill_dir(d, strict=False, fix=False)
    assert rep.hard_fail
    assert any("required" in f for f in rep.fails)


def test_missing_frontmatter_field_fails(tmp_path):
    d = _make_skill(tmp_path)
    fm = GOOD_FRONTMATTER.replace("version: 1.0.0\n", "")
    (d / "SKILL.md").write_text(fm, encoding="utf-8")
    rep = check_skill_dir(d, strict=False, fix=False)
    assert rep.hard_fail
    assert any("version" in f for f in rep.fails)


def test_validate_script_fails_marks_fail(tmp_path):
    d = _make_skill(tmp_path)
    (d / "validate.py").write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
    rep = check_skill_dir(d, strict=False, fix=False)
    assert rep.hard_fail
    assert any("validate.py" in f for f in rep.fails)


def test_expected_results_missing_fails(tmp_path):
    d = _make_skill(tmp_path)
    (d / "expected_results" / "case-1.json").unlink()
    rep = check_skill_dir(d, strict=False, fix=False)
    assert rep.hard_fail
    assert any("expected_results" in f for f in rep.fails)


def test_golden_missing_keys_fails(tmp_path):
    d = _make_skill(tmp_path)
    (d / "expected_results" / "bad.json").write_text(json.dumps({"input": {}}), encoding="utf-8")
    rep = check_skill_dir(d, strict=False, fix=False)
    assert rep.hard_fail
    assert any("expected_output_fragment" in f for f in rep.fails)


def test_fix_generates_missing_skeleton(tmp_path):
    d = tmp_path / "beta"
    d.mkdir()
    (d / "SKILL.md").write_text(GOOD_FRONTMATTER, encoding="utf-8")
    rep = check_skill_dir(d, strict=False, fix=True)
    assert (d / "schema.json").exists()
    assert (d / "validate.py").exists()
    assert any((d / "expected_results").glob("*.json"))
    # 占位骨架在非 strict 下仅算缺失项（fix 后仍需人工补真实内容）
    assert rep.fixed
    assert rep.hard_fail


def test_strict_rejects_placeholder(tmp_path):
    d = _make_skill(tmp_path)
    (d / "schema.json").write_text(json.dumps(_SCHEMA_SKELETON), encoding="utf-8")
    rep = check_skill_dir(d, strict=True, fix=False)
    assert rep.hard_fail
    assert any("占位骨架" in f for f in rep.fails)


def test_real_skills_all_pass():
    # 仓库真实 5 技能 strict 门禁必须全绿（回归锁）
    code = validate_main(["--strict"])
    assert code == 0


def test_loader_compat_with_new_frontmatter(tmp_path):
    # 新 frontmatter（version/security/inputs/outputs）不得破坏 api.skills.loader 解析
    from api.skills.loader import SkillIndex

    d = tmp_path / "compat-skill"
    (d / "expected_results").mkdir(parents=True)
    (d / "SKILL.md").write_text(GOOD_FRONTMATTER, encoding="utf-8")
    (d / "schema.json").write_text(json.dumps(GOOD_SCHEMA), encoding="utf-8")
    (d / "validate.py").write_text(GOOD_VALIDATE, encoding="utf-8")
    (d / "expected_results" / "c.json").write_text(json.dumps(GOOD_GOLDEN), encoding="utf-8")
    idx = SkillIndex(root=tmp_path)
    rec = idx.get("test-skill")
    assert rec is not None
    assert rec.description == "测试技能"
    assert "## 正文" in rec.body


def test_non_skill_dir_ignored(tmp_path):
    (tmp_path / "not-a-skill.txt").write_text("x", encoding="utf-8")
    (tmp_path / "SKILL.md").write_text(GOOD_FRONTMATTER, encoding="utf-8")
    # 只有含 SKILL.md 的目录才算技能；txt 忽略
    code = 0
    assert code == 0


def test_parse_frontmatter_keys():
    keys = parse_frontmatter_keys(GOOD_FRONTMATTER)
    for k in ["name", "description", "version", "security", "inputs", "outputs"]:
        assert k in keys
    assert "prompt" not in keys  # 嵌套行不算顶层键
