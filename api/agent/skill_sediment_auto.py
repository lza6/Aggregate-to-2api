"""技能自动沉淀（指南 v18 P0-1，SkillClaw + SkillOpt 对标；证伪实验 sediment_probe 已确认区分度 0.306）。

对 DAG run 终态（succeeded）自动生成候选技能草稿：
1. 开关/状态/幂等/上限四重前置检查（零副作用失败）
2. 生成候选 SKILL.md：默认**规则模板**（零 LLM 零付费）；仅当 IF_SKILL_AUTO_BUDGET_USD>0 且预算门禁放行时才尝试 LLM 摘要
3. 复用 v17 `scan_skill` 安全闸门（risk_score >= 阈值拒绝入库）
4. 复用 sediment_probe 评估器做重放验证 → gate_score 记录（>= 既有技能均分*IF_SKILL_GATE_THRESHOLD 预标记可批）
5. 写 `skill_sediment_store` 草稿（source=auto，仍须人工审批才生效）

挂载：agent_dag run 终态后调用 `maybe_sediment_run(run)`（静默降级，不阻塞主链路）。
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger("agent.skill_sediment_auto")

# 探针任务集（与 sediment_probe.PROBE_PROMPTS 保持一致，供重放验证打分）；
# scripts 非包：注入目录后按模块导入（同 api/agent/skill_scan.py 模式）
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from sediment_probe import PROBE_PROMPTS, replay_score  # noqa: E402


def _cfg() -> Any:
    from ..config import get_settings

    return get_settings()


def _auto_enabled() -> bool:
    return bool(_cfg().if_skill_sediment_auto)


def _max_draft() -> int:
    return max(1, int(_cfg().if_skill_max_draft or 50))


def _gate_threshold() -> float:
    return float(_cfg().if_skill_gate_threshold or 0.8)


def _auto_budget_usd() -> float:
    return float(_cfg().if_skill_auto_budget_usd or 0.0)


def build_candidate_md(run: Any) -> dict[str, Any]:
    """从 DAG run 快照生成候选技能元数据（规则模板：run 名/首节点 prompt）。"""
    run_id = str(getattr(run, "run_id", "") or "")
    name = str(getattr(run, "name", "") or "").strip()[:60] or "DAG 自动沉淀技能"
    nodes = getattr(run, "nodes", None) or []
    prompt = ""
    scene = ""
    for n in nodes:
        p = (n.get("prompt") or "") if isinstance(n, dict) else (getattr(n, "prompt", "") or "")
        k = (n.get("kind") or "") if isinstance(n, dict) else (getattr(n, "kind", "") or "")
        if p:
            prompt = p
        if k == "scene":
            scene = (n.get("scene") or "") if isinstance(n, dict) else (getattr(n, "scene", "") or "")
    description = f"由 DAG run {run_id[:8]} 自动沉淀的技能（{scene or '通用'}）"
    return {
        "run_id": run_id,
        "name": name,
        "description": description,
        "prompt_template": prompt or name,
        "params": {"scene": scene, "source": "auto"},
    }


def _existing_mean_score() -> float:
    """既有技能在探针任务集上的均分（复用评估器，本地零成本）。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "api" / "skills"
    dirs = [d for d in sorted(root.iterdir()) if d.is_dir() and (d / "SKILL.md").exists()]
    if not dirs:
        return 0.5
    scores = []
    for d in dirs:
        s = [replay_score(p, d) for p in PROBE_PROMPTS]
        scores.append(sum(s) / len(s))
    return sum(scores) / len(scores)


async def gate_score_for(run: Any) -> float:
    """候选技能重放验证分（0-1）：写临时目录 → 探针评估器打分。纯本地无 LLM。"""
    import tempfile
    from pathlib import Path

    from .skill_sediment import build_skill_md

    meta = build_candidate_md(run)
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "candidate"
        d.mkdir()
        (d / "SKILL.md").write_text(
            build_skill_md(name=meta["name"], description=meta["description"], prompt_template=meta["prompt_template"], params=meta["params"], notes="auto-sediment"),
            encoding="utf-8",
        )
        scores = [replay_score(p, d) for p in PROBE_PROMPTS]
    return round(sum(scores) / len(scores), 4)


def _draft_count(items: list[dict[str, Any]]) -> int:
    return sum(1 for it in items if it.get("status") == "draft")


async def _already_sedimented(run_id: str) -> bool:
    from .skill_sediment import skill_sediment_store as store

    items = await store.list_skills()
    return any(it.get("source_run_id") == run_id for it in items)


async def maybe_sediment_run(run: Any) -> bool:
    """DAG run 终态自动沉淀入口。返回 True=已生成草稿；False=未生成（开关关/状态不符/拒绝/上限）。

    任何异常静默降级（记 warning，不阻塞主链路）。
    """
    try:
        if not _auto_enabled():
            return False
        status = str(getattr(run, "status", "") or "")
        if status != "succeeded":
            return False
        run_id = str(getattr(run, "run_id", "") or "")
        if not run_id:
            return False
        if await _already_sedimented(run_id):
            return False

        from .skill_scan import scan_skill
        from .skill_sediment import skill_sediment_store as store

        drafts = await store.list_skills()
        if _draft_count(drafts) >= _max_draft():
            log.warning("skill auto-sediment: 草稿达上限 %s，跳过 run %s", _max_draft(), run_id)
            return False

        meta = build_candidate_md(run)
        content = f"{meta['name']}\n{meta['description']}\n{meta['prompt_template']}"
        scan = scan_skill(content)
        if scan.rejected:
            log.warning("skill auto-sediment: run %s 未过安全扫描（risk=%s），拒绝入库", run_id, scan.risk_score)
            return False

        gate = await gate_score_for(run)
        baseline = _existing_mean_score()
        preapproved = gate >= baseline * _gate_threshold()
        notes = f"auto-sediment gate={gate} baseline={round(baseline, 4)} preapproved={preapproved}"

        row = await store.save_draft(
            name=meta["name"],
            description=meta["description"],
            prompt_template=meta["prompt_template"],
            params=meta["params"],
            source_run_id=run_id,
            risk_score=scan.risk_score,
            scan_findings=scan.findings,
            notes=notes,
        )
        log.info("skill auto-sediment: run %s → 草稿 %s（gate=%s preapproved=%s）", run_id, row.get("id"), gate, preapproved)
        return True
    except Exception as exc:  # noqa: BLE001 - 自动沉淀必须静默降级
        log.warning("skill auto-sediment 异常（降级跳过）run=%s: %s", getattr(run, "run_id", "?"), exc)
        return False
