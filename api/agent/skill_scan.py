"""技能安全扫描闸门封装（指南 B1b / P0-2，SkillSpector 对标）。

供技能沉淀/上传入口调用：``scan_skill(content) -> SkillScanResult``。
- 开关 IF_SKILL_SCAN_ENABLED=0 → 放行（零风险不拒绝）
- risk_score >= IF_SKILL_SCAN_REJECT（缺省 60）→ rejected=True
纯静态 AST/正则，禁止执行/联网；复用 scripts/skillspector.py 同一套规则（不复制实现）。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from skillspector import ScanOutcome, load_baseline, scan_content  # noqa: E402


@dataclass
class SkillScanResult:
    """技能扫描结果（供沉淀/上传入口消费）。"""

    risk_score: int = 0
    rejected: bool = False
    threshold: int = 60
    findings: list[dict[str, Any]] = field(default_factory=list)
    suppressed_count: int = 0
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_score": self.risk_score,
            "rejected": self.rejected,
            "threshold": self.threshold,
            "suppressed_count": self.suppressed_count,
            "findings_count": len(self.findings),
            "findings": self.findings,
        }


def _scan_config() -> tuple[bool, int]:
    """读取 IF_SKILL_SCAN_ENABLED / IF_SKILL_SCAN_REJECT（缺省 1 / 60）。"""
    from api.config import get_settings

    security = get_settings().security
    enabled = bool(getattr(security, "skill_scan_enabled", True))
    reject = int(getattr(security, "skill_scan_reject", 60) or 60)
    return enabled, reject


def scan_skill(content: str) -> SkillScanResult:
    """对技能内容执行静态安全扫描，返回闸门判定。

    - 开关关闭（IF_SKILL_SCAN_ENABLED=0）→ 返回 enabled=False、零风险、不拒绝
    - risk_score >= IF_SKILL_SCAN_REJECT → rejected=True（上游应拒绝入库）
    """
    enabled, reject = _scan_config()
    if not enabled:
        return SkillScanResult(enabled=False)
    baseline = load_baseline(_SCRIPTS_DIR / "baseline.yaml")
    outcome: ScanOutcome = scan_content(content, baseline=baseline, threshold=reject)
    active = [f for f in outcome.findings if not f.suppressed]
    return SkillScanResult(
        risk_score=outcome.risk_score,
        rejected=outcome.rejected,
        threshold=outcome.threshold,
        findings=[f.to_dict() for f in active],
        suppressed_count=len(outcome.findings) - len(active),
    )
