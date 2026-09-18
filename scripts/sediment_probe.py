"""技能自动沉淀证伪实验（指南 v18 P0-1，RT-1 反证先行）。

问题：『历史 DAG 重放验证能否可靠判断候选技能好坏』——若区分度不足则保持手动收藏制。
本探针用**确定性 Mock 评估器**（零 LLM/零付费）对 5 个已知好/坏技能重放打分：
- 好技能：仓库 api/skills/*（四件套完整 + golden 样例，v17 已工程化）
- 坏技能：临时构造（缺 schema/validate/expected_results + 空 SKILL.md）
打分 = 0.5*技能质量分 + 0.5*意图相关度（关键词共现，无 LLM）
区分度 = mean(好) - mean(坏)；> 阈值(0.15) → 自动沉淀「可尝试」；否则「保持手动」。

用法:
    python scripts/sediment_probe.py            # 全量探针报告
    python scripts/sediment_probe.py --json     # JSON 输出
退出码: 0 = 可区分（自动沉淀可尝试）；1 = 区分不足（建议保持手动）；2 = 参数错误。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = ROOT / "api" / "skills"

# 区分度阈值：好/坏平均分差 >= 0.15 视为评估器可区分（否则重放验证不可靠）
DISCRIMINATION_THRESHOLD = 0.15

# 覆盖 8 个典型任务意图（image/ecommerce/ppt/critic/quality/chat/video/memory 方向）
PROBE_PROMPTS = (
    "帮我把这款蓝牙耳机做成电商主图",
    "写一份产品发布会 PPT 大纲",
    "生成一张深色背景的城市夜景图",
    "对刚生成的图片做质量终检",
    "检查这张图是否有水印和重复",
    "给客户写一段电商详情页文案",
    "用一句话描述想做的视频",
    "记住我喜欢深色背景风格",
)

# 四件套质量分权重
PIECE_WEIGHTS = {"SKILL.md": 0.4, "schema.json": 0.2, "validate.py": 0.2, "expected_results": 0.2}


@dataclass
class ProbeReport:
    """证伪实验结果。"""

    good: list[dict] = field(default_factory=list)
    bad: list[dict] = field(default_factory=list)
    mean_good: float = 0.0
    mean_bad: float = 0.0
    discrimination: float = 0.0
    passed: bool = False
    threshold: float = DISCRIMINATION_THRESHOLD


def skill_quality(skill_dir: Path) -> float:
    """技能质量分（0-1）：四件套完整度 + golden 样例数 + SKILL.md 体量。"""
    score = 0.0
    total_w = 0.0
    for piece, w in PIECE_WEIGHTS.items():
        total_w += w
        target = skill_dir / piece
        exists = target.exists()
        score += w * (1.0 if exists else 0.0)
        if piece == "expected_results" and exists:
            goldens = list(target.glob("*.json"))
            score += w * min(1.0, len(goldens) / 2.0) * 0.5  # ≥2 个 golden 满分
    md = skill_dir / "SKILL.md"
    if md.exists():
        try:
            body_len = len(md.read_text(encoding="utf-8"))
        except OSError:
            body_len = 0
        if body_len >= 500:
            score += 0.1 * total_w
        elif body_len >= 200:
            score += 0.05 * total_w
    return round(min(1.0, score / total_w), 4)


def _tokens(text: str) -> set[str]:
    """轻量分词：中文按 2-gram + 英文按词。"""
    text = text.lower()
    toks: set[str] = set()
    for m in re.finditer(r"[a-z0-9_]{2,}", text):
        toks.add(m.group(0))
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    for i in range(len(cjk) - 1):
        toks.add(cjk[i] + cjk[i + 1])
    return toks


def relevance(prompt: str, skill_desc: str) -> float:
    """意图相关度（0-1）：prompt 与技能描述的关键词共现（Jaccard 近似）。"""
    a, b = _tokens(prompt), _tokens(skill_desc)
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return round(inter / len(a | b), 4)


def replay_score(prompt: str, skill: Path) -> float:
    """单次重放分 = 0.5*质量 + 0.5*相关度。"""
    desc = ""
    md = skill / "SKILL.md"
    if md.exists():
        text = md.read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if m:
            for line in m.group(1).splitlines():
                key, _, val = line.partition(":")
                if key.strip().lower() == "description":
                    desc = val.strip()
                    break
    q = skill_quality(skill)
    r = relevance(prompt, desc)
    return round(0.5 * q + 0.5 * r, 4)


def build_bad_skills(tmpdir: Path, count: int = 5) -> list[Path]:
    """构造坏技能（缺四件套 + 空 SKILL.md）。"""
    dirs: list[Path] = []
    for i in range(count):
        d = tmpdir / f"bad-skill-{i}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            f"---\nname: bad-skill-{i}\ndescription: 一个没有任何实质内容的技能占位\n---\n（内容缺失）\n",
            encoding="utf-8",
        )
        dirs.append(d)
    return dirs


def run_probe(good_dirs: list[Path], bad_dirs: list[Path], prompts: tuple[str, ...]) -> ProbeReport:
    rep = ProbeReport()
    for g in good_dirs:
        scores = [replay_score(p, g) for p in prompts]
        rep.good.append({"name": g.name, "quality": skill_quality(g), "mean_score": round(sum(scores) / len(scores), 4), "per_prompt": scores})
    for b in bad_dirs:
        scores = [replay_score(p, b) for p in prompts]
        rep.bad.append({"name": b.name, "quality": skill_quality(b), "mean_score": round(sum(scores) / len(scores), 4)})
    rep.mean_good = round(sum(x["mean_score"] for x in rep.good) / len(rep.good), 4) if rep.good else 0.0
    rep.mean_bad = round(sum(x["mean_score"] for x in rep.bad) / len(rep.bad), 4) if rep.bad else 0.0
    rep.discrimination = round(rep.mean_good - rep.mean_bad, 4)
    rep.passed = rep.discrimination >= rep.threshold
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="技能自动沉淀证伪实验（RT-1）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args(argv)

    good_dirs = [d for d in sorted(SKILLS_ROOT.iterdir()) if d.is_dir() and (d / "SKILL.md").exists()]
    if len(good_dirs) < 3:
        print(f"[probe] 好技能不足（{len(good_dirs)}<3），中止")
        return 2
    with tempfile.TemporaryDirectory() as td:
        bad_dirs = build_bad_skills(Path(td))
        rep = run_probe(good_dirs, bad_dirs, PROBE_PROMPTS)

    if args.json:
        print(json.dumps({
            "mean_good": rep.mean_good, "mean_bad": rep.mean_bad,
            "discrimination": rep.discrimination, "threshold": rep.threshold,
            "passed": rep.passed, "good": rep.good, "bad": rep.bad,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"[probe] 好技能均分={rep.mean_good}  坏技能均分={rep.mean_bad}  区分度={rep.discrimination} (阈值 {rep.threshold})")
        print(f"[probe] 结论: {'自动沉淀评估器可区分好/坏 → 可尝试自动沉淀（仍建议审批前置）' if rep.passed else '区分度不足 → 保持手动收藏制（勿强行自动化）'}")
    return 0 if rep.passed else 1


if __name__ == "__main__":
    sys.exit(main())
