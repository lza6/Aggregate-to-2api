"""技能安全扫描器（指南 B1b / P0-2，SkillSpector 对标）。

对 SKILL.md / 技能附件做 4 类纯静态扫描（禁止执行/联网）：
  1. prompt_injection        prompt 注入（系统指令覆盖/角色越权/分隔符逃逸）
  2. data_exfiltration       数据外泄（环境变量/密钥/敏感文件路径读取）
  3. escalation_destruction  提权与破坏（复用 agent.guard.is_destructive_command + 补充规则）
  4. supply_chain            供应链（URL 下载执行/可疑依赖名/内联远程脚本）

输出 0-100 风险分 + 命中明细 + baseline 白名单抑制。风险分 = 命中权重求和（封顶 100）。

用法:
    python scripts/skillspector.py skill.md                  # 扫描文件
    python scripts/skillspector.py - < skill.md              # 扫描 stdin
    python scripts/skillspector.py --json - < skill.md       # JSON 输出
    python scripts/skillspector.py --baseline baseline.yaml  # 指定白名单
    python scripts/skillspector.py --threshold 60            # 覆盖拒绝阈值

退出码: 0 = 通过（score < threshold）；1 = 拒绝；2 = 用法错误。
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 使 `import api.agent.guard` 可从仓库任意 cwd 生效
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api.agent.guard import is_destructive_command  # noqa: E402

# 权重：单个 critical 即达缺省拒绝阈值（60）
_W_CRITICAL = 60
_W_HIGH = 35
_W_MEDIUM = 20
_W_LOW = 10
_W_INFO = 4


@dataclass(frozen=True)
class Rule:
    rule_id: str
    category: str
    severity: str
    pattern: re.Pattern
    detail: str
    weight: int


def _rx(p: str) -> re.Pattern:
    return re.compile(p, re.IGNORECASE)


RULES: tuple[Rule, ...] = (
    # ── prompt_injection ────────────────────────────────────────────────
    Rule("inj_delimiter_system", "prompt_injection", "critical",
         _rx(r"(<\|im_start\|>system|</system>|<<SYS>>|\[SYSTEM\]|### System Instructions|## System Prompt)"),
         "系统指令分隔符逃逸，可覆盖宿主系统提示词", _W_CRITICAL),
    Rule("inj_ignore_previous", "prompt_injection", "high",
         _rx(r"(ignore (all |any )?(previous|above|prior) (instructions|prompts|messages|context)|disregard (all |any )?(previous|above|prior) (instructions|prompts))"),
         "指示忽略宿主既有指令（prompt 注入特征）", _W_HIGH),
    Rule("inj_role_override", "prompt_injection", "high",
         _rx(r"you are (now )?(acting as )?(dan|jailbreak|unrestricted|no (rules|restrictions|boundaries)|not (an? )?(assistant|ai|llm|chatbot))"),
         "角色越权/解禁暗示", _W_HIGH),
    Rule("inj_new_system_prompt", "prompt_injection", "high",
         _rx(r"(your (new |real )?system prompt (is|should be)|the following instructions take precedence|new instructions override)"),
         "声明新指令优先，覆盖宿主上下文", _W_HIGH),
    Rule("inj_end_of_prompt", "prompt_injection", "medium",
         _rx(r"\[END OF PROMPT\]|\[END OF (INSTRUCTION|MESSAGE)\]|###END###"),
         "伪造 prompt 结束标记诱骗后续拼接", _W_MEDIUM),

    # ── data_exfiltration ───────────────────────────────────────────────
    Rule("exfil_env_read", "data_exfiltration", "medium",
         _rx(r"os\.environ\[|os\.getenv\(|os\.environ\.get|process\.env\.|getenv\("),
         "读取环境变量（可能含密钥）", _W_MEDIUM),
    Rule("exfil_secret_literal", "data_exfiltration", "high",
         _rx(r"(sk-[a-z0-9]{16,}|AKIA[0-9a-z]{16}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|ghp_[a-z0-9]{20,})"),
         "明文密钥/令牌字面量", _W_HIGH),
    Rule("exfil_secret_file", "data_exfiltration", "high",
         _rx(r"(/etc/passwd|/etc/shadow|/proc/self/environ|~/?\.ssh/id_|\.aws/credentials|id_rsa|id_ed25519|credentials\.json)"),
         "读取敏感文件路径", _W_HIGH),
    Rule("exfil_cred_pair", "data_exfiltration", "medium",
         _rx(r"(api[_-]?key|secret|token|password)\s*[:=]\s*[\"']?[a-z0-9_\-@!#$%^&*?.]{8,}"),
         "疑似凭据赋值", _W_MEDIUM),

    # ── escalation_destruction ──────────────────────────────────────────
    Rule("dest_sudo_rm_root", "escalation_destruction", "critical",
         _rx(r"(sudo\s+)?rm\s+-[a-z]*r[a-z]*f?\s+/\s*($|\s)"),
         "递归强删根目录", _W_CRITICAL),
    Rule("dest_fs_destroy", "escalation_destruction", "critical",
         _rx(r"(mkfs(\.[a-z0-9]+)?|dd if=/dev/zero of=/dev/|:\(\)\s*\{\s*:\|:&\s*\};:)"),
         "文件系统销毁/分叉炸弹", _W_CRITICAL),
    Rule("dest_priv_escalation", "escalation_destruction", "high",
         _rx(r"(chmod\s+-r?w?x?\s*777\s+(/|/[\w/]+)|chown\s+-r?\s*0:0?\s+/|useradd.*-o.*-u\s*0|pkexec\s+sh\s+-c)"),
         "提权/全局权限放开", _W_HIGH),
    Rule("dest_system_cmd", "escalation_destruction", "high",
         _rx(r"(shutdown(\s+-h|\s+/s)|reboot(\s+-f)?|iptables\s+-f|systemctl\s+disable\s+|mount\s+--bind)"),
         "高危系统命令", _W_HIGH),

    # ── supply_chain ────────────────────────────────────────────────────
    Rule("sup_curl_pipe_shell", "supply_chain", "critical",
         _rx(r"(curl|wget)\s+[^|;&\n]*\s*(\|\s*(sh|bash|zsh)|;?\s*(sh|bash)\s+-c\s+[\"'])"),
         "远程下载后直接执行（供应链投毒高风险）", _W_CRITICAL),
    Rule("sup_install_from_url", "supply_chain", "high",
         _rx(r"(pip|pip3|npm|yarn|gem|cargo)\s+(install|add|i)\s+[^\s]*(git\+https?://|https?://)"),
         "从 URL 安装依赖（非注册表）", _W_HIGH),
    Rule("sup_download_exec", "supply_chain", "high",
         _rx(r"(Invoke-WebRequest|Invoke-Expression|curl\.exe|wget\.exe|DownloadFile|shell_exec\()|(curl\s+-o\s+[\w./]+|wget\s+-O\s+[\w./]+)"),
         "下载可执行文件/远程执行", _W_HIGH),
    Rule("sup_suspicious_dep", "supply_chain", "high",
         _rx(r"(pip|pip3|npm|yarn|gem|cargo|apt(-get)?)\s+(install|add|i|update)\s+[\w.\-]*(xmrig|minerd|cpuminer|keylog|steal|hack|backdoor|trojan|malware|spy|phish)[\w.\-]*"),
         "可疑依赖名（挖矿/窃密/木马系）", _W_HIGH),
    Rule("sup_raw_url_codeblock", "supply_chain", "low",
         _rx(r"https?://(raw\.githubusercontent\.com|gist\.githubusercontent\.com|pastebin\.com|transfer\.sh|0x0\.st|termbin\.com)"),
         "代码块内可疑远程 URL", _W_LOW),
)


@dataclass
class Finding:
    rule_id: str
    category: str
    severity: str
    weight: int
    match: str
    line: int
    detail: str
    suppressed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class ScanOutcome:
    risk_score: int = 0
    findings: list[Finding] = field(default_factory=list)
    rejected: bool = False
    threshold: int = 60
    scanned_lines: int = 0
    baseline: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_score": self.risk_score,
            "rejected": self.rejected,
            "threshold": self.threshold,
            "scanned_lines": self.scanned_lines,
            "baseline": self.baseline,
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass(frozen=True)
class BaselineEntry:
    rule_id: str | None = None
    category: str | None = None
    pattern: str | None = None


def parse_baseline(text: str) -> list[BaselineEntry]:
    """解析最小 YAML 子集 baseline（无第三方依赖）。

    格式:
        rules:
          - rule_id: exfil_env_read
            pattern: "example.com"
          - category: supply_chain
            comment: ...
    """
    entries: list[BaselineEntry] = []
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "rules:":
            continue
        if line.startswith("- "):
            if current:
                entries.append(BaselineEntry(**current))
            current = {}
            line = line[2:].strip()
        if current is None:
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key in {"rule_id", "category", "pattern"}:
                current[key] = val
    if current:
        entries.append(BaselineEntry(**current))
    return entries


def load_baseline(path: Path | None) -> list[BaselineEntry]:
    if path is None or not path.exists():
        return []
    try:
        return parse_baseline(path.read_text(encoding="utf-8"))
    except OSError:
        return []


def _is_suppressed(f: Finding, baseline: list[BaselineEntry]) -> bool:
    for b in baseline:
        if b.rule_id and b.rule_id.lower() == f.rule_id.lower():
            return True
        if b.category and b.category.lower() == f.category.lower():
            return True
        if b.pattern and re.search(b.pattern, f.match, re.IGNORECASE):
            return True
    return False


def _extract_code_lines(content: str) -> list[str]:
    """提取代码围栏/内联命令，用于破坏性命令判定。"""
    out: list[str] = []
    for m in re.finditer(r"```[^\n]*\n(.*?)```", content, re.DOTALL):
        out.append(m.group(1))
    for m in re.finditer(r"`([^`\n]{2,200})`", content):
        seg = m.group(1).strip()
        if any(ch in seg for ch in (" ", "=", "|", ";", "&")) and not seg.startswith(("http", "#", "//")):
            out.append(seg)
    return out


def scan_content(content: str, baseline: list[BaselineEntry] | None = None, threshold: int = 60) -> ScanOutcome:
    """执行全部静态扫描，返回风险结果。纯静态，不执行/不联网。"""
    baseline = baseline or []
    findings: list[Finding] = []
    lines = content.splitlines()

    # 1) 正则规则
    for i, line in enumerate(lines, start=1):
        for rule in RULES:
            m = rule.pattern.search(line)
            if not m:
                continue
            findings.append(Finding(
                rule_id=rule.rule_id,
                category=rule.category,
                severity=rule.severity,
                weight=rule.weight,
                match=m.group(0)[:120],
                line=i,
                detail=rule.detail,
            ))

    # 2) 破坏性命令（复用 agent.guard.is_destructive_command）
    for block in _extract_code_lines(content):
        for cmd in block.splitlines():
            cmd = cmd.strip()
            if not cmd or cmd.startswith(("#", "//", "REM")):
                continue
            if is_destructive_command(cmd):
                findings.append(Finding(
                    rule_id="dest_guard_shared",
                    category="escalation_destruction",
                    severity="critical",
                    weight=_W_CRITICAL,
                    match=cmd[:120],
                    line=next((i for i, ln in enumerate(lines, 1) if cmd in ln), 0),
                    detail="命中 agent.guard.is_destructive_command 共享黑名单",
                ))

    # 3) baseline 抑制
    for f in findings:
        if _is_suppressed(f, baseline):
            f.suppressed = True

    active = [f for f in findings if not f.suppressed]
    risk_score = min(100, sum(f.weight for f in active))
    return ScanOutcome(
        risk_score=risk_score,
        findings=findings,
        rejected=risk_score >= threshold,
        threshold=threshold,
        scanned_lines=len(lines),
    )


def _default_baseline_path() -> Path:
    return Path(__file__).resolve().parent / "baseline.yaml"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="技能安全扫描器（SkillSpector 对标）")
    ap.add_argument("file", nargs="?", help="技能内容文件；缺省读 stdin")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--baseline", default=None, help="baseline yaml 路径（缺省 scripts/baseline.yaml）")
    ap.add_argument("--no-baseline", action="store_true", help="禁用 baseline 抑制")
    ap.add_argument("--threshold", type=int, default=None, help="拒绝阈值（缺省 IF_SKILL_SCAN_REJECT 或 60）")
    args = ap.parse_args(argv)

    if args.file == "-" or args.file is None:
        content = sys.stdin.read()
    else:
        try:
            content = Path(args.file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"[skillspector] 读取失败: {exc}")
            return 2

    threshold = args.threshold
    if threshold is None:
        try:
            from api.config import get_settings
            threshold = int(get_settings().security.skill_scan_reject or 60)
        except Exception:  # noqa: BLE001
            threshold = 60

    baseline_path = None if args.no_baseline else Path(args.baseline) if args.baseline else _default_baseline_path()
    baseline = [] if args.no_baseline else load_baseline(baseline_path)

    outcome = scan_content(content, baseline=baseline, threshold=threshold)
    if args.json:
        data = outcome.to_dict()
        data["baseline"] = str(baseline_path) if (baseline_path and baseline) else None
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"risk_score: {outcome.risk_score} ({'REJECTED' if outcome.rejected else 'PASS'})  threshold={outcome.threshold}")
        for f in outcome.findings:
            tag = " [suppressed]" if f.suppressed else ""
            print(f"  [{f.severity}]{tag} {f.rule_id} @ line {f.line}: {f.match}")
    return 1 if outcome.rejected else 0


if __name__ == "__main__":
    sys.exit(main())
