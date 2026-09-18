"""技能工程化四件套一键门禁（指南 B1a / P0-4，anthropics 规范对标）。

用法:
    python scripts/validate_skills.py            # 默认校验全部技能，硬 FAIL 即退出码 1
    python scripts/validate_skills.py --strict   # CI 口径：警告也视为失败 + 拒绝占位骨架
    python scripts/validate_skills.py --fix      # 生成缺失的 schema.json/validate.py/expected_results 骨架

校验项（每技能）:
- SKILL.md frontmatter 必需字段: name/description/version/security/inputs/outputs
- schema.json 可解析且为 object + properties + required
- validate.py 可执行（以当前解释器运行，输出 PASS、退出码 0）
- expected_results/ 非空且 golden JSON 含 input + expected_output_fragment
--strict 额外: 拒绝自动生成骨架标记（placeholder），并视警告为失败。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = ROOT / "api" / "skills"
REQUIRED_FRONTMATTER = ["name", "description", "version", "security", "inputs", "outputs"]

# --fix 生成的骨架里带此标记，--strict 下视为占位拒绝
_PLACEHOLDER_MARK = "__skeleton__"

_VALIDATE_SKELETON = '''"""__skeleton__ 占位骨架：由 scripts/validate_skills.py --fix 生成，请补充真实校验逻辑。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent


def validate() -> tuple[bool, str]:
    return True, "PASS: 占位骨架（待补充）"


def main() -> int:
    ok, summary = validate()
    print(summary)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
'''

_SCHEMA_SKELETON = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "__skeleton__ input schema",
    "type": "object",
    "additionalProperties": True,
    "properties": {},
    "required": [],
}

_GOLDEN_SKELETON = {
    "name": "__skeleton__-case",
    "description": "占位黄金样例（--fix 生成）",
    "input": {},
    "expected_output_fragment": {},
}


@dataclass
class SkillReport:
    name: str
    ok: bool = True
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.fails.append(msg)

    def warn(self, msg: str) -> None:
        self.warns.append(msg)

    @property
    def hard_fail(self) -> bool:
        return bool(self.fails)


def parse_frontmatter_keys(text: str) -> set[str]:
    """提取 frontmatter 顶层键（与 api/skills/loader.py 宽容解析同构）。"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        return set()
    return {
        line.partition(":")[0].strip().lower()
        for line in m.group(1).splitlines()
        if ":" in line and not line.startswith((" ", "\t"))
    }


def check_skill_dir(skill_dir: Path, strict: bool, fix: bool) -> SkillReport:
    rep = SkillReport(name=skill_dir.name)

    md = skill_dir / "SKILL.md"
    if not md.exists():
        rep.fail("SKILL.md 缺失")
    else:
        text = md.read_text(encoding="utf-8")
        keys = parse_frontmatter_keys(text)
        missing = [k for k in REQUIRED_FRONTMATTER if k not in keys]
        if missing:
            rep.fail(f"frontmatter 缺字段: {', '.join(missing)}")

    schema_path = skill_dir / "schema.json"
    if not schema_path.exists():
        rep.fail("schema.json 缺失")
        if fix:
            schema_path.write_text(json.dumps(_SCHEMA_SKELETON, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            rep.fixed.append("schema.json")
    else:
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            if schema.get("type") != "object":
                rep.fail("schema.type != object")
            if not isinstance(schema.get("properties"), dict):
                rep.fail("schema.properties 缺失或非 dict")
            if not isinstance(schema.get("required"), list):
                rep.fail("schema.required 缺失或非 list")
            if strict and _PLACEHOLDER_MARK in json.dumps(schema):
                rep.fail("schema 为 --fix 占位骨架（strict 拒绝）")
        except Exception as exc:  # noqa: BLE001
            rep.fail(f"schema.json 解析失败: {exc}")

    vp = skill_dir / "validate.py"
    if not vp.exists():
        rep.fail("validate.py 缺失")
        if fix:
            vp.write_text(_VALIDATE_SKELETON, encoding="utf-8")
            rep.fixed.append("validate.py")
    else:
        if strict and _PLACEHOLDER_MARK in vp.read_text(encoding="utf-8"):
            rep.fail("validate.py 为占位骨架（strict 拒绝）")
        try:
            # 子进程 stdout 编码随父进程环境变化（GBK/UTF-8 均有可能），
            # 用 bytes 模式 + errors=replace 显式 UTF-8 解码，避免 locale 解码异常。
            r = subprocess.run([sys.executable, str(vp)], capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            rep.fail("validate.py 执行超时（60s）")
        else:
            out = (r.stdout or b"").decode("utf-8", errors="replace") + (r.stderr or b"").decode("utf-8", errors="replace")
            if r.returncode != 0 or "PASS" not in out:
                rep.fail(f"validate.py 执行失败 exit={r.returncode}: {out.strip()[:200]}")
            elif strict and _PLACEHOLDER_MARK in out:
                rep.fail("validate.py 输出占位标记（strict 拒绝）")

    edir = skill_dir / "expected_results"
    if not edir.exists() or not any(edir.glob("*.json")):
        rep.fail("expected_results 缺失或无 golden JSON")
        if fix:
            edir.mkdir(exist_ok=True)
            (edir / "README.md").write_text("# 黄金样例\n\n每个 `.json` 含 input 与 expected_output_fragment。\n", encoding="utf-8")
            (edir / f"{skill_dir.name}-skeleton.json").write_text(json.dumps(_GOLDEN_SKELETON, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            rep.fixed.append("expected_results")
    else:
        for g in sorted(edir.glob("*.json")):
            try:
                data = json.loads(g.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                rep.fail(f"golden {g.name} 解析失败: {exc}")
                continue
            if "input" not in data or "expected_output_fragment" not in data:
                rep.fail(f"golden {g.name} 缺 input/expected_output_fragment")
            if strict and _PLACEHOLDER_MARK in json.dumps(data):
                rep.fail(f"golden {g.name} 为占位骨架（strict 拒绝）")
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="技能四件套门禁")
    ap.add_argument("--strict", action="store_true", help="CI 口径：警告视为失败 + 拒绝占位骨架")
    ap.add_argument("--fix", action="store_true", help="生成缺失骨架（不修改 SKILL.md 业务内容）")
    args = ap.parse_args(argv)

    if not SKILLS_ROOT.exists():
        print(f"[validate_skills] 未找到技能目录: {SKILLS_ROOT}")
        return 2

    reports: list[SkillReport] = []
    for skill_dir in sorted(SKILLS_ROOT.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("__"):
            continue
        if not (skill_dir / "SKILL.md").exists():
            continue
        reports.append(check_skill_dir(skill_dir, strict=args.strict, fix=args.fix))

    if not reports:
        print("[validate_skills] 未发现任何技能（无 SKILL.md）")
        return 2

    print(f"[validate_skills] 共 {len(reports)} 个技能")
    failed = 0
    for rep in reports:
        status = "PASS" if not rep.hard_fail else "FAIL"
        if rep.hard_fail:
            failed += 1
        detail = f"  [{status}] {rep.name}"
        if rep.fixed:
            detail += f" (已生成: {', '.join(rep.fixed)})"
        print(detail)
        for f in rep.fails:
            print(f"    - {f}")
        for w in rep.warns:
            print(f"    ~ {w}")
    print(f"[validate_skills] 结果: {len(reports) - failed}/{len(reports)} PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
