"""sediment_probe 证伪实验测试（v18 P0-1，RT-1）。纯本地确定性。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.sediment_probe import (  # noqa: E402
    PROBE_PROMPTS,
    build_bad_skills,
    replay_score,
    run_probe,
    skill_quality,
)


def _good_dirs():
    from scripts.sediment_probe import SKILLS_ROOT

    return [d for d in sorted(SKILLS_ROOT.iterdir()) if d.is_dir() and (d / "SKILL.md").exists()]


def test_skill_quality_good_full(tmp_path):
    d = tmp_path / "good"
    (d / "expected_results").mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: g\ndescription: 测试技能\nversion: 1.0.0\n---\n" + "正文" * 300, encoding="utf-8")
    (d / "schema.json").write_text('{"type":"object"}', encoding="utf-8")
    (d / "validate.py").write_text("pass\n", encoding="utf-8")
    (d / "expected_results" / "a.json").write_text("{}", encoding="utf-8")
    (d / "expected_results" / "b.json").write_text("{}", encoding="utf-8")
    assert skill_quality(d) >= 0.8


def test_skill_quality_bad_missing_pieces(tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    (d / "SKILL.md").write_text("（内容缺失）", encoding="utf-8")
    assert skill_quality(d) <= 0.45  # 仅有 SKILL.md（weight 0.4），四件套残缺


def test_relevance_overlap():
    from scripts.sediment_probe import relevance

    assert relevance("电商主图", "电商主图 详情页") > 0
    assert relevance("视频生成", "PPT 大纲") == 0.0


def test_replay_score_range(tmp_path):
    d = tmp_path / "s"
    (d / "expected_results").mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: s\ndescription: 电商主图视觉策划\n---\n正文内容", encoding="utf-8")
    (d / "schema.json").write_text("{}", encoding="utf-8")
    (d / "validate.py").write_text("pass\n", encoding="utf-8")
    s = replay_score("帮我把这款蓝牙耳机做成电商主图", d)
    assert 0.0 <= s <= 1.0
    assert s > 0.3


def test_probe_discriminates_good_vs_bad(tmp_path):
    good = _good_dirs()
    assert len(good) >= 3
    bad = build_bad_skills(tmp_path, count=3)
    rep = run_probe(good, bad, PROBE_PROMPTS)
    assert rep.mean_good > rep.mean_bad
    assert rep.discrimination >= 0.15
    assert rep.passed is True


def test_probe_report_fields():
    from scripts.sediment_probe import ProbeReport

    r = ProbeReport()
    assert r.mean_good == 0.0 and r.mean_bad == 0.0 and r.threshold == 0.15
