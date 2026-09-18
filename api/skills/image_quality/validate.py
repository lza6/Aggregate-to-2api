"""技能自检脚本（四件套之一，anthropics 规范对标）。独立可运行：python validate.py

校验：schema.json 合法性 + expected_results 黄金样例 + SKILL.md frontmatter 必需字段。
纯标准库，无第三方依赖；输出 PASS/FAIL，退出码 0/1。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
_REQUIRED_FM = ["name", "description", "version", "security", "inputs", "outputs"]


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _check_schema(report: list[str]) -> bool:
    path = DIR / "schema.json"
    if not path.exists():
        report.append("FAIL: schema.json 缺失")
        return False
    try:
        schema = _load_json(path)
    except Exception as exc:  # noqa: BLE001
        report.append(f"FAIL: schema.json 解析失败 {exc}")
        return False
    ok = True
    if schema.get("type") != "object":
        report.append("FAIL: schema.type != object")
        ok = False
    if not isinstance(schema.get("properties"), dict):
        report.append("FAIL: schema.properties 缺失或非 dict")
        ok = False
    if not isinstance(schema.get("required"), list):
        report.append("FAIL: schema.required 缺失或非 list")
        ok = False
    return ok


def _conforms(schema: dict, data: dict, report: list[str]) -> bool:
    """迷你 schema 一致性检查（required + 基本类型/enum/pattern），非完整 JSON Schema 校验。"""
    ok = True
    props = schema.get("properties", {})
    for req in schema.get("required", []):
        if req not in data:
            report.append(f"FAIL: golden input 缺 required 字段 {req}")
            ok = False
        else:
            p = props.get(req, {})
            t = p.get("type")
            if t == "string" and not isinstance(data[req], str):
                report.append(f"FAIL: 字段 {req} 类型应为 string")
                ok = False
            elif t == "integer" and not isinstance(data[req], int):
                report.append(f"FAIL: 字段 {req} 类型应为 integer")
                ok = False
            elif t == "boolean" and not isinstance(data[req], bool):
                report.append(f"FAIL: 字段 {req} 类型应为 boolean")
                ok = False
            elif t == "array" and not isinstance(data[req], list):
                report.append(f"FAIL: 字段 {req} 类型应为 array")
                ok = False
            elif t == "object" and not isinstance(data[req], dict):
                report.append(f"FAIL: 字段 {req} 类型应为 object")
                ok = False
            if "enum" in p and data[req] not in p["enum"]:
                report.append(f"FAIL: 字段 {req} 不在枚举 {p['enum']}")
                ok = False
            if "pattern" in p and isinstance(data[req], str) and not re.search(p["pattern"], data[req]):
                report.append(f"FAIL: 字段 {req} 不匹配 pattern {p['pattern']}")
                ok = False
    return ok


def _check_expected(report: list[str]) -> bool:
    edir = DIR / "expected_results"
    if not edir.exists():
        report.append("FAIL: expected_results 目录缺失")
        return False
    goldens = sorted(edir.glob("*.json"))
    if not goldens:
        report.append("FAIL: expected_results 无 golden JSON")
        return False
    ok = True
    for g in goldens:
        try:
            data = _load_json(g)
        except Exception as exc:  # noqa: BLE001
            report.append(f"FAIL: golden {g.name} 解析失败 {exc}")
            ok = False
            continue
        if "input" not in data or "expected_output_fragment" not in data:
            report.append(f"FAIL: golden {g.name} 缺 input/expected_output_fragment")
            ok = False
            continue
        schema = _load_json(DIR / "schema.json")
        if not _conforms(schema, data["input"], report):
            ok = False
    return ok


def _check_frontmatter(report: list[str]) -> bool:
    md = DIR / "SKILL.md"
    if not md.exists():
        report.append("FAIL: SKILL.md 缺失")
        return False
    text = md.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        report.append("FAIL: SKILL.md 无 frontmatter")
        return False
    keys = {line.partition(":")[0].strip().lower() for line in m.group(1).splitlines() if ":" in line}
    ok = True
    for k in _REQUIRED_FM:
        if k not in keys:
            report.append(f"FAIL: frontmatter 缺字段 {k}")
            ok = False
    return ok


def validate() -> tuple[bool, str]:
    report: list[str] = []
    ok, _ = _check_frontmatter(report), None
    if ok:
        ok = _check_schema(report)
    if ok:
        ok = _check_expected(report)
    summary = "PASS: 四件套校验通过（frontmatter/schema/golden）" if ok else "FAIL: " + "；".join(report)
    return ok, summary


def main() -> int:
    ok, summary = validate()
    print(summary)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
