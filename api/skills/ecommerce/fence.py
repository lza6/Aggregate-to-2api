"""电商技能合规护栏（指南 P1-5，commerce-agents + feichanggege 对标）。

电商文案的合规红线（广告法）：
- 绝对化用语：最/第一/国家级/顶级/极致/100% 等（无依据不可用）
- 医疗功效宣称：治愈/根治/抗癌/降血糖 等（普通商品不可宣称）
- 数据宣称：需要背书来源

fence 输出：driver + campaign_style + storyboard + prompts 结构化内容先过
``check_compliance`` 扫描；命中红线 → rejected + 替代方向建议（不生成违规文案）。
纯静态词表 + 正则，零 LLM 依赖，单测可锁定。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ComplianceIssue:
    rule: str  # absolute_claim / medical_claim / data_claim
    match: str
    detail: str


@dataclass
class FenceResult:
    ok: bool
    issues: list[ComplianceIssue] = field(default_factory=list)
    alternative: str = ""

    @property
    def rejected(self) -> bool:
        return not self.ok


_ABSOLUTE_TERMS = (
    "最", "第一", "第一品牌", "国家级", "世界级", "顶级", "极致", "唯一",
    "绝对", "100%", "百分百", "全网最低", "史上最低", "永久免费",
)
_MEDICAL_TERMS = (
    "治愈", "根治", "抗癌", "防癌", "降血糖", "降血压", "减肥", "燃脂",
    "治疗", "消炎", "杀菌", "祛除湿气", "药到病除",
)
# 无背书声明则视为可疑数据宣称
_DATA_PATTERNS = re.compile(r"\d+\s*(%|倍|天|小时|分钟|kg|斤|℃|dB|瓦|W|小时续航|级降噪)\b|负[0-9.]+dB", re.IGNORECASE)


def check_compliance(text: str) -> list[ComplianceIssue]:
    """扫描文本命中合规红线，返回问题列表（空=通过）。"""
    issues: list[ComplianceIssue] = []
    for term in _ABSOLUTE_TERMS:
        if term in text:
            issues.append(ComplianceIssue(
                rule="absolute_claim", match=term,
                detail=f"绝对化用语「{term}」需可验证背书，否则不得使用（广告法）",
            ))
    for term in _MEDICAL_TERMS:
        if term in text:
            issues.append(ComplianceIssue(
                rule="medical_claim", match=term,
                detail=f"医疗功效宣称「{term}」普通商品不可使用",
            ))
    for m in _DATA_PATTERNS.finditer(text):
        issues.append(ComplianceIssue(
            rule="data_claim", match=m.group(0),
            detail=f"数据宣称「{m.group(0)}」需附来源/检测背书",
        ))
    return issues


def fence_ecommerce_payload(
    driver: str | None = None,
    campaign_style: dict[str, Any] | None = None,
    storyboard: list[dict[str, Any]] | None = None,
    prompts: list[str] | None = None,
    self_review: dict[str, Any] | None = None,
) -> FenceResult:
    """对电商执行稿 payload 过合规闸门。

    - 命中 absolute/medical 红线 → rejected + 替代方向
    - 数据宣称仅提示（data_claim 可由用户补充背书后放行，决策保留给用户/审批）
    """
    collected: list[str] = []
    collected.append(driver or "")
    if campaign_style:
        collected.append(str(campaign_style))
    if storyboard:
        collected.extend(str(item) for item in storyboard)
    if prompts:
        collected.extend(prompts)
    if self_review:
        collected.append(str(self_review))
    text = "\n".join(collected)

    issues = check_compliance(text)
    hard = [i for i in issues if i.rule in ("absolute_claim", "medical_claim")]
    if hard:
        return FenceResult(
            ok=False,
            issues=issues,
            alternative="改为可验证数据表述（如实验室检测报告数字）或模糊定性表述（如「显著降噪」需附背书）",
        )
    return FenceResult(ok=True, issues=issues)
